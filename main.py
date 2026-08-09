import flet as ft
import os
import sqlite3
import requests
import re
import threading
import time
from datetime import datetime
from bs4 import BeautifulSoup

# --- ИМПОРТЫ ДЛЯ ИИ И ЗВУКА ---
import google.generativeai as genai
from gtts import gTTS
import flet_audio as fta             
import flet_audio_recorder as far    

# --- НАСТРОЙКА GEMINI ---
GEMINI_API_KEY = "AQ.Ab8RN6JoDV-Afqq1tBI1iJh43G9_PqfqjgXh6hF1xsZPBYgeyQ"  # <--- ЗАМЕНИ НА СВОЙ КЛЮЧ!
genai.configure(api_key=GEMINI_API_KEY)
ai_model = genai.GenerativeModel('gemini-1.5-flash')

DB_FOLDER = "databases"
os.makedirs(DB_FOLDER, exist_ok=True)

class InventoryMobileApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Склад Knigoman"
        self.page.padding = 0
        self.page.window_width = 400
        self.page.window_height = 800

        self.auto_user = "shared_account"
        self.auto_pass = "qQ7bXXxfwa"
        self.web_session = requests.Session()
        self.admin_token = ""
        
        self.scanned_items = set()

        # === НЕВИДИМЫЕ АУДИОКОМПОНЕНТЫ ДЛЯ ИИ ===
        # Используем новые выделенные библиотеки для звука
        self.audio_player = fta.Audio(autoplay=False)
        self.audio_recorder = far.AudioRecorder()
        self.page.overlay.extend([self.audio_player, self.audio_recorder])

        self.build_ui()

        saved_theme = self.load_theme()
        self.theme_dropdown.value = saved_theme
        self.apply_theme(saved_theme)

        self.auto_sync_thread = threading.Thread(target=self.auto_update_loop, daemon=True)
        self.auto_sync_thread.start()
        
        # При запуске пытаемся подтянуть названия сборок с сайта
        threading.Thread(target=self.fetch_collections, daemon=True).start()

    def load_theme(self):
        try:
            if os.path.exists("theme.txt"):
                with open("theme.txt", "r", encoding="utf-8") as f:
                    return f.read().strip()
        except: pass
        return "dark"

    def save_theme(self, theme_name):
        try:
            with open("theme.txt", "w", encoding="utf-8") as f:
                f.write(theme_name)
        except: pass

    def change_theme(self, e):
        val = self.theme_dropdown.value
        self.save_theme(val)
        self.apply_theme(val)

    def apply_theme(self, theme_name):
        if theme_name == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.page.bgcolor = None
            self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        elif theme_name == "knigoman":
            self.page.theme_mode = ft.ThemeMode.LIGHT
            self.page.bgcolor = None
            self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.ORANGE)
        elif theme_name == "black":
            self.page.theme_mode = ft.ThemeMode.DARK
            self.page.bgcolor = ft.Colors.BLACK
            self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        else: # dark
            self.page.theme_mode = ft.ThemeMode.DARK
            self.page.bgcolor = None
            self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE)
        self.page.update()

    # --- DROPBOX: АВТО-ОБНОВЛЕНИЕ И ВЫГРУЗКА ---
    def auto_update_loop(self):
        while True:
            time.sleep(1800)
            self.silent_download_db()

    def silent_download_db(self):
        saved_db_url = ""
        try:
            if os.path.exists("settings.txt"):
                with open("settings.txt", "r", encoding="utf-8") as f:
                    saved_db_url = f.read().strip()
        except: pass

        if not saved_db_url: return
        dropbox_link = saved_db_url.replace("?dl=0", "?dl=1") if "?dl=0" in saved_db_url else saved_db_url
        if "?dl=1" not in dropbox_link: dropbox_link += "?dl=1"

        try:
            response = requests.get(dropbox_link, timeout=30)
            if response.status_code == 200:
                db_path = os.path.join(DB_FOLDER, "inventory.db")
                with open(db_path, 'wb') as f:
                    f.write(response.content)
                now = datetime.now().strftime("%H:%M")
                if hasattr(self, 'db_status'):
                    self.db_status.value = f"✅ База обновлена в {now}!"
                    self.db_status.color = ft.Colors.GREEN_700
                    self.page.update()
        except: pass

    def silent_upload_db(self):
        def task():
            db_path = os.path.join(DB_FOLDER, "inventory.db")
            if not os.path.exists(db_path): return
            try:
                import dropbox
                from dropbox.files import WriteMode
                dbx = dropbox.Dropbox(
                    app_key="qxk5xqzdx6355bs",
                    app_secret="c6zydckwlybtk2w",
                    oauth2_refresh_token="to5DsS-qwgAAAAAAAAAAAaY0tLxVdICbafBvJKFGSF2NFzN9mtNLqfKm7sslAt_C"
                )
                with open(db_path, "rb") as f:
                    dbx.files_upload(f.read(), "/inventory_latest.db", mode=WriteMode.overwrite)
            except Exception as e:
                pass
        threading.Thread(target=task, daemon=True).start()

    def download_and_extract_db(self, e):
        url_input = self.db_input.value.strip()
        if not url_input:
            self.db_status.value = "Введите ссылку Dropbox!"
            self.db_status.color = ft.Colors.RED_600
            self.page.update()
            return

        self.db_btn.disabled = True
        self.db_progress.visible = True
        self.db_status.value = "⏳ Скачивание базы..."
        self.db_status.color = ft.Colors.BLUE_600
        self.page.update()

        try:
            with open("settings.txt", "w", encoding="utf-8") as f:
                f.write(url_input)
        except: pass

        dropbox_link = url_input.replace("?dl=0", "?dl=1") if "?dl=0" in url_input else url_input
        if "?dl=1" not in dropbox_link: dropbox_link += "?dl=1"

        try:
            response = requests.get(dropbox_link, timeout=15)
            if response.status_code == 200:
                db_path = os.path.join(DB_FOLDER, "inventory.db")
                with open(db_path, 'wb') as f:
                    f.write(response.content)
                self.db_status.value = f"✅ Готово! База успешно загружена."
                self.db_status.color = ft.Colors.GREEN_700
            else:
                self.db_status.value = "❌ Ошибка скачивания."
                self.db_status.color = ft.Colors.RED_600
        except Exception as ex:
            self.db_status.value = f"❌ Ошибка: {str(ex)}"
            self.db_status.color = ft.Colors.RED_600
        
        self.db_btn.disabled = False
        self.db_progress.visible = False
        self.page.update()

    # --- SQLITE ЧТЕНИЕ И УДАЛЕНИЕ ---
    def load_databases(self):
        master_db = {}
        db_path = os.path.join(DB_FOLDER, "inventory.db")
        if not os.path.exists(db_path): return master_db
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, location FROM books")
            books = cursor.fetchall()
            cursor.execute("SELECT book_id, code_value, code_type FROM barcodes")
            barcodes = cursor.fetchall()
            book_codes = {}
            for b_id, val, ctype in barcodes:
                if b_id not in book_codes: book_codes[b_id] = {"Штрихкод": "", "Balka code": ""}
                if ctype == 'barcode': book_codes[b_id]["Штрихкод"] = val
                elif ctype == 'balka': book_codes[b_id]["Balka code"] = val
            for b_id, title, loc in books:
                if loc not in master_db: master_db[loc] = {}
                master_db[loc][title] = book_codes.get(b_id, {"Штрихкод": "", "Balka code": ""})
            conn.close()
        except Exception as e: pass
        return master_db

    def delete_book_from_cell(self, book):
        db_path = os.path.join(DB_FOLDER, "inventory.db")
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM books WHERE title=? AND location=?", (book['title'], book['location']))
            row = cursor.fetchone()
            if row:
                book_id = row[0]
                cursor.execute("DELETE FROM barcodes WHERE book_id=?", (book_id,))
                cursor.execute("DELETE FROM books WHERE id=?", (book_id,))
                conn.commit()
            conn.close()
            
            self.search_status.value = f"Удалено: {book['title'][:20]}..."
            self.search_status.color = ft.Colors.GREEN_500
            self.perform_search(None) 
            self.silent_upload_db() 
        except Exception as e:
            self.search_status.value = f"Ошибка удаления: {e}"
            self.search_status.color = ft.Colors.RED_500
            self.page.update()

    # --- ИНТЕРФЕЙС И ВКЛАДКИ ---
    def build_ui(self):
        saved_db_url = ""
        try:
            if os.path.exists("settings.txt"):
                with open("settings.txt", "r", encoding="utf-8") as f:
                    saved_db_url = f.read().strip()
        except: pass

        # === ВКЛАДКА СБОРКИ ===
        self.ass_collection_dropdown = ft.Dropdown(
            label="Найденные сборки", 
            options=[ft.dropdown.Option(key="", text="🔄 Ищу на сайте...")], 
            expand=True
        )
        self.ass_refresh_col_btn = ft.IconButton(
            icon=ft.Icons.REFRESH, 
            icon_color=ft.Colors.CYAN_500, 
            tooltip="Обновить список сборок", 
            on_click=self.fetch_collections
        )
        
        self.ass_manual_input = ft.TextField(
            label="Или впишите (напр. 09_2)", 
            width=180
        )
        self.ass_delivery_dropdown = ft.Dropdown(
            label="Доставка",
            options=[
                ft.dropdown.Option(key="np", text="📦 Новая Почта"),
                ft.dropdown.Option(key="up", text="✉️ Укрпочта"),
                ft.dropdown.Option(key="rozetka", text="🟢 Розетка"),
                ft.dropdown.Option(key="all", text="Все вместе (Любая)")
            ],
            value="np",
            expand=True
        )
        
        self.ass_btn = ft.FilledButton("Собрать список", on_click=self.build_assembly_list, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
        self.ass_status = ft.Text("Ожидание действий...", color=ft.Colors.GREEN_500)
        self.ass_progress = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        self.ass_listview = ft.ListView(expand=True, spacing=10, padding=10)
        
        self.view_assembly = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([self.ass_collection_dropdown, self.ass_refresh_col_btn]),
                    ft.Row([self.ass_manual_input, self.ass_delivery_dropdown]),
                    ft.Row([self.ass_btn]),
                    ft.Row([self.ass_progress, self.ass_status])
                ]),
                padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            ),
            self.ass_listview
        ], expand=True, visible=False)

        # === ВКЛАДКА РАССТАНОВКИ ===
        self.place_input = ft.TextField(
            label="Штрихкод / Название", 
            hint_text="Ввод или скан...", 
            expand=True, 
            on_submit=self.perform_place_search 
        )
        self.place_clear_btn = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP, 
            icon_color=ft.Colors.RED_400, 
            on_click=self.clear_place_list, 
            tooltip="Очистить список"
        )
        self.place_save_btn = ft.FilledButton("Сохранить ячейку", on_click=self.save_place_session, bgcolor=ft.Colors.GREEN_700, visible=False)
        
        self.place_listview = ft.ListView(expand=True, spacing=10, padding=10)

        self.view_place = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("Добавление (пикайте сканером):", weight="bold", size=16),
                        ft.Container(expand=True), 
                        self.place_clear_btn
                    ]),
                    ft.Row([self.place_input]),
                    self.place_save_btn
                ]),
                padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            ),
            self.place_listview
        ], expand=True, visible=False)

        # === ВКЛАДКА ПОИСКА И УДАЛЕНИЯ ===
        self.search_input = ft.TextField(label="Название, штрихкод или Balka", expand=True)
        self.search_btn = ft.FilledButton("Искать", on_click=self.perform_search, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
        self.search_status = ft.Text("", color=ft.Colors.GREEN_700)
        self.search_progress = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        self.search_listview = ft.ListView(expand=True, spacing=10, padding=10)

        self.view_search = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([self.search_input, self.search_btn]),
                    ft.Row([self.search_progress, self.search_status])
                ]),
                padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            ),
            self.search_listview
        ], expand=True, visible=False)

        # === НОВАЯ ВКЛАДКА: ИИ-АССИСТЕНТ (РАЦИЯ) ===
        self.ai_status = ft.Text("Готов. Нажми и говори", color=ft.Colors.GREEN_500, size=18, weight="bold", text_align=ft.TextAlign.CENTER)
        self.ai_progress = ft.ProgressRing(width=30, height=30, stroke_width=3, visible=False)
        
        self.record_btn = ft.FloatingActionButton(
            icon=ft.Icons.MIC,
            bgcolor=ft.Colors.PURPLE_700,
            on_click=self.toggle_recording,
            width=80, height=80
        )

        self.view_ai = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Text("🤖 Голосовой Кладовщик", weight="bold", size=22, color=ft.Colors.PURPLE_400),
                    ft.Container(height=40),
                    ft.Row([self.record_btn], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Container(height=40),
                    ft.Row([self.ai_progress], alignment=ft.MainAxisAlignment.CENTER),
                    ft.Row([self.ai_status], alignment=ft.MainAxisAlignment.CENTER)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=30, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=15, expand=True
            )
        ], expand=True, visible=False)

        # === ВКЛАДКА БАЗЫ (DROPBOX) ===
        self.db_input = ft.TextField(label="Прямая ссылка Dropbox", expand=True, value=saved_db_url)
        self.db_btn = ft.FilledButton("Загрузить базу сейчас", on_click=self.download_and_extract_db, bgcolor=ft.Colors.PURPLE_700, color=ft.Colors.WHITE)
        self.db_status = ft.Text("База скачивается автоматически.", color=ft.Colors.ORANGE_700)
        self.db_progress = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        
        self.view_db = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Text("Настройки базы", weight="bold", size=18),
                    self.db_input, 
                    self.db_btn, 
                    ft.Row([self.db_progress, self.db_status])
                ]),
                padding=20, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            )
        ], expand=True, visible=True)

        # === ВКЛАДКА НАСТРОЕК ===
        self.theme_dropdown = ft.Dropdown(
            label="Стиль интерфейса",
            options=[
                ft.dropdown.Option(key="dark", text="Темная тема"),
                ft.dropdown.Option(key="black", text="AMOLED Черная"),
                ft.dropdown.Option(key="light", text="Светлая тема"),
                ft.dropdown.Option(key="knigoman", text="Как на сайте (Knigoman)")
            ],
            on_select=self.change_theme
        )

        self.view_settings = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Text("Настройки приложения", weight="bold", size=18),
                    self.theme_dropdown
                ]),
                padding=20, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            )
        ], expand=True, visible=False)

        # === ГЛАВНЫЙ КОНТЕЙНЕР ===
        self.main_container = ft.Container(
            content=ft.Stack([
                self.view_assembly, 
                self.view_place,    
                self.view_search,
                self.view_ai,      # <--- Вкладка ИИ
                self.view_db, 
                self.view_settings
            ]),
            expand=True, padding=10
        )

        self.page.navigation_bar = ft.NavigationBar(
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.SHOPPING_CART, label="Сборка"),
                ft.NavigationBarDestination(icon=ft.Icons.MOVE_TO_INBOX, label="Места"), 
                ft.NavigationBarDestination(icon=ft.Icons.SEARCH, label="Поиск"),
                ft.NavigationBarDestination(icon=ft.Icons.RECORD_VOICE_OVER, label="ИИ"),
                ft.NavigationBarDestination(icon=ft.Icons.FOLDER, label="База"),
                ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Настройки"),
            ],
            on_change=self.on_nav_change,
            selected_index=5
        )

        self.page.add(ft.SafeArea(content=self.main_container, expand=True))

    def on_nav_change(self, e):
        idx = e.control.selected_index
        self.view_assembly.visible = (idx == 0)
        self.view_place.visible = (idx == 1)
        self.view_search.visible = (idx == 2)
        self.view_ai.visible = (idx == 3)
        self.view_db.visible = (idx == 4)
        self.view_settings.visible = (idx == 5)
        self.page.update()

    # ================= ЛОГИКА ИИ-АССИСТЕНТА (РАЦИЯ) =================
    def toggle_recording(self, e):
        audio_path = os.path.join(DB_FOLDER, "request.m4a")
        
        if self.record_btn.icon == ft.Icons.MIC:
            self.record_btn.icon = ft.Icons.STOP
            self.record_btn.bgcolor = ft.Colors.RED_600
            self.ai_status.value = "Слушаю... (Нажми для остановки)"
            self.ai_status.color = ft.Colors.RED_500
            self.page.update()
            
            try:
                self.audio_recorder.start_recording(audio_path)
            except Exception as ex:
                self.ai_status.value = "Разреши доступ к микрофону!"
                self.ai_status.color = ft.Colors.ORANGE_500
                self.record_btn.icon = ft.Icons.MIC
                self.record_btn.bgcolor = ft.Colors.PURPLE_700
                self.page.update()
        else:
            self.audio_recorder.stop_recording()
            self.record_btn.icon = ft.Icons.MIC
            self.record_btn.bgcolor = ft.Colors.PURPLE_700
            self.record_btn.disabled = True
            
            self.ai_progress.visible = True
            self.ai_status.value = "Думаю..."
            self.ai_status.color = ft.Colors.CYAN_500
            self.page.update()
            
            threading.Thread(target=self.process_voice_request, args=(audio_path,), daemon=True).start()

    def process_voice_request(self, audio_path):
        time.sleep(0.5) 
        try:
            if not os.path.exists(audio_path):
                raise Exception("Аудиофайл не записался")

            audio_file = genai.upload_file(path=audio_path)
            
            db = self.load_databases()
            catalog = []
            for loc, books in db.items():
                for title in books.keys():
                    catalog.append(f"'{title}' -> {loc}")
            
            if not catalog:
                context = "В базе данных нет ни одной книги."
            else:
                context = "\n".join(catalog)
            
            prompt = (
                f"Ты складской помощник. В прикрепленном аудио пользователь задает вопрос о товаре.\n"
                f"Найди ответ, опираясь строго на эту базу данных (формат 'Название' -> 'Стеллаж, Ячейка'):\n{context}\n\n"
                "Отвечай коротко и четко. Назови только место (стеллаж и ячейку). Если в базе нет такого товара, скажи 'Не найдено'. "
                "Твой ответ будет озвучен роботом, пиши только текст для озвучки (без звездочек и спецсимволов)."
            )
            
            response = ai_model.generate_content([prompt, audio_file])
            answer_text = response.text.replace('*', '').strip()
            
            genai.delete_file(audio_file.name)
            
            self.ai_status.value = "Озвучиваю..."
            self.page.update()

            tts = gTTS(text=answer_text, lang='ru')
            answer_audio = os.path.join(DB_FOLDER, "answer.mp3")
            tts.save(answer_audio)

            self.ai_status.value = answer_text
            self.ai_status.color = ft.Colors.GREEN_400
            
            self.audio_player.src = answer_audio
            self.audio_player.play()

        except Exception as ex:
            self.ai_status.value = f"Сбой связи или тишина: {str(ex)[:30]}"
            self.ai_status.color = ft.Colors.RED_500
            
        finally:
            self.record_btn.disabled = False
            self.ai_progress.visible = False
            self.page.update()

    # --- УМНЫЙ ПОИСК И УСКОРЕННАЯ АВТОРИЗАЦИЯ ---
    def smart_match(self, site_title, db_title):
        s = site_title.lower()
        d = db_title.lower()
        if s in d or d in s: return True
        s_norm = ' '.join(re.sub(r'[^\w\s]', '', s).split())
        d_norm = ' '.join(re.sub(r'[^\w\s]', '', d).split())
        if s_norm and d_norm and (s_norm in d_norm or d_norm in s_norm): return True
        s_words = s_norm.split()
        d_words = d_norm.split()
        if len(s_words) >= 3 and len(d_words) >= 3:
            if s_words[:3] == d_words[:3]: return True
        s_significant = [w for w in s_words if len(w) > 2]
        d_significant = [w for w in d_words if len(w) > 2]
        if s_significant and d_significant:
            matches = sum(1 for w in s_significant if w in d_significant)
            if matches / len(s_significant) >= 0.7: return True
        return False

    def perform_login(self, status_label=None, is_silent=False):
        if status_label and not is_silent:
            status_label.value = "Быстрый вход на сайт..."
            status_label.color = ft.Colors.CYAN_500
            self.page.update()
        
        login_url = "https://knigoman.com.ua/admin/index.php?route=common/login"
        self.web_session.headers.update({'User-Agent': 'Mozilla/5.0'})
        try:
            if not is_silent:
                self.web_session.get(login_url, timeout=5)
            payload = {'username': self.auto_user, 'password': self.auto_pass, 'redirect': 'https://knigoman.com.ua/admin/index.php?route=common/home'}
            response = self.web_session.post(login_url, data=payload, timeout=8)
            
            if 'token=' in response.url:
                self.admin_token = re.search(r'token=([^&]+)', response.url).group(1)
                if status_label and not is_silent:
                    status_label.value = "Вход выполнен!"
                    status_label.color = ft.Colors.GREEN_500
                    self.page.update()
                return True
            return False
        except Exception:
            return False

    def clean_book_specs(self, full_text, title):
        text = full_text.replace(title, "", 1).strip()
        balka_match = re.search(r'балка\s*[:-]?\s*([a-zA-Z0-9а-яА-Я]+)', text.lower())
        balka_text = f"Балка: {balka_match.group(1).upper()}" if balka_match else ""
        text_lower = text.lower()
        for word in ['шинко', 'застела', 'резерв']:
            idx = text_lower.find(word)
            if idx != -1:
                text = text[:idx]
                text_lower = text_lower[:idx] 
        good_keywords = ['твердая', 'мягкая', 'палитурка', 'обложка', 'бумага', 'цвет', 'покет', 'а5', 'увеличенный', 'формат', 'укр', 'рус', 'рос']
        words = text.replace('|', ' ').split()
        temp_phrase = []
        for word in words:
            w_lower = word.lower()
            if re.match(r'^\(?\d+([.,]\d+)?\)?$', w_lower): continue
            if 'балка' in w_lower or (balka_match and balka_match.group(1).lower() in w_lower): continue
            if any(junk in w_lower for junk in ['грн', 'id:', 'артикул', 'isbn', 'шт.', 'кол-во', 'модель']): continue
            if any(good in w_lower for good in good_keywords) or len(word) > 3: temp_phrase.append(word)
        cleaned = " ".join(temp_phrase)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -.,|;()') 
        final_result = []
        if cleaned: final_result.append(cleaned)
        if balka_text: final_result.append(balka_text)
        if final_result: return f" ({' | '.join(final_result)})"
        return ""

    def parse_items_from_soup(self, soup):
        found_items = []
        product_links = soup.find_all('a', href=re.compile(r'route=catalog/product/edit'))
        if product_links:
            for a in product_links:
                title = a.text.strip()
                if not title: continue
                text_container = a.find_parent(['td', 'div'])
                text_content = text_container.get_text(separator=" ", strip=True) if text_container else a.text
                
                qty_text = ""
                if text_container:
                    attention_span = text_container.find('span', class_='attention')
                    if attention_span and 'шт' in attention_span.text.lower():
                        qty_match = re.search(r'(\d+)', attention_span.text)
                        if qty_match: qty_text = f"🔥 НУЖНО {qty_match.group(1)} ШТ. 🔥"
                
                if not qty_text:
                    qty_match = re.search(r'!\s*(\d+)\s*шт', text_content.lower())
                    if qty_match: qty_text = f"🔥 НУЖНО {qty_match.group(1)} ШТ. 🔥"

                clean_specs = self.clean_book_specs(text_content, title)
                
                img_tag = None
                if text_container:
                    img_tag = text_container.find('img')
                    if not img_tag:
                        prev = text_container.find_previous_sibling()
                        if prev: img_tag = prev if prev.name == 'img' else prev.find('img')
                img_url = img_tag.get('src') if img_tag else None
                
                order_id = ""
                order_product_id = ""
                status_id = "25"
                row = a.find_parent('tr')
                row_html = str(row) if row else ""
                
                if row:
                    m_opid = re.search(r'collectionToAssembled\([^,]+,\s*(\d+)\)', row_html)
                    if m_opid: order_product_id = m_opid.group(1)
                    m_stat = re.search(r'data-status-id="(\d+)"', row_html)
                    if m_stat: status_id = m_stat.group(1)

                    order_input = row.find('input', {'name': re.compile(r'order_id')})
                    if order_input: order_id = order_input.get('value', '')
                    if not order_id:
                        m_oid = re.search(r'order_id=(\d+)', row_html)
                        if m_oid: order_id = m_oid.group(1)

                display_info = f"{title}{clean_specs}"
                found_items.append({
                    "title": title, "display_title": display_info, "full_text": text_content, 
                    "img_url": img_url, "order_product_id": order_product_id, 
                    "status_id": status_id, "order_id": order_id, "qty_text": qty_text,
                    "row_html": row_html
                })
        return found_items

    def mark_collected(self, e, item):
        btn = e.control
        btn.disabled = True
        btn.text = "⏳"
        btn.update()
        o_id, op_id, s_id = item.get("order_id"), item.get("order_product_id"), item.get("status_id", "25")
        if not op_id or not o_id:
            btn.text = "❌"
            btn.update()
            return
        def send_request():
            ajax_url = "https://knigoman.com.ua/index.php?route=crm/crm_api/changeField"
            payload = {'order_id': str(o_id), 'field': 'order_status_id', 'field_name': 'Статус заказа', 'value': str(s_id), 'custom_field': 'false', 'user_id': '36'}
            headers = {'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'}
            return self.web_session.post(ajax_url, data=payload, headers=headers, timeout=10)
        try:
            if not self.admin_token: self.perform_login()
            response = send_request()
            if "login" in response.url.lower() or response.status_code == 403:
                if self.perform_login(skip_get=True): response = send_request() 
                else:
                    btn.text, btn.bgcolor = "❌", ft.Colors.RED_700
                    btn.update()
                    return
            if response.status_code == 200: btn.text, btn.bgcolor = "✅", ft.Colors.GREEN_700
            else: btn.text, btn.bgcolor = "❌", ft.Colors.RED_700
        except Exception: btn.text, btn.bgcolor = "❌", ft.Colors.RED_700
        btn.update()

    def check_book_in_db(self, item, db):
        locations = []
        site_full_text = item.get("full_text", "").lower()
        for loc, books in db.items():
            for db_title, info in books.items():
                db_balka = str(info.get("Balka code", "")).strip().lower()
                title_matched = self.smart_match(item["title"], db_title)
                balka_matched = False
                if db_balka and len(db_balka) > 3 and db_balka in site_full_text: balka_matched = True
                if title_matched or balka_matched:
                    if loc not in locations: locations.append(loc)
        if locations: return " | ".join(locations), ft.Colors.GREEN_700
        return "Нет в базах", ft.Colors.RED_400

    # ================= ЛОГИКА СБОРКИ С САЙТА =================
    def fetch_collections(self, e=None):
        is_silent = (e is None)
        
        if not is_silent:
            self.ass_status.value = "Поиск активных сборок..."
            self.ass_progress.visible = True
            self.ass_btn.disabled = True
            self.page.update()

        if not self.admin_token and not self.perform_login(self.ass_status if not is_silent else None, is_silent=is_silent):
            self.ass_collection_dropdown.options = [ft.dropdown.Option(key="", text="❌ Ошибка логина")]
            self.ass_collection_dropdown.value = ""
            if not is_silent: self.ass_progress.visible = False
            self.page.update()
            return

        try:
            url = f"https://knigoman.com.ua/admin/index.php?route=crm/order&token={self.admin_token}&filter_order_status=23&filter_limit=150"
            response = self.web_session.get(url, timeout=10)
            
            if "route=common/login" in response.url or "token=" not in response.url:
                if self.perform_login(self.ass_status if not is_silent else None, is_silent=is_silent):
                    url = f"https://knigoman.com.ua/admin/index.php?route=crm/order&token={self.admin_token}&filter_order_status=23&filter_limit=150"
                    response = self.web_session.get(url, timeout=10)
                else:
                    raise Exception("Не удалось залогиниться")
                    
            soup = BeautifulSoup(response.text, 'html.parser')
            opts_dict = {}

            for row in soup.find_all('tr'):
                row_text = row.get_text(separator=" ", strip=True)
                m_name = re.search(r'(\d+_\d+)', row_text)
                if m_name:
                    col_name = m_name.group(1)
                    for a in row.find_all('a'):
                        href = a.get('href', '')
                        m_id = re.search(r'filter_collection=(\d+)', href)
                        if m_id:
                            opts_dict[m_id.group(1)] = col_name

            opts = []
            for k, v in opts_dict.items():
                opts.append(ft.dropdown.Option(key=k, text=f"Сборка {v}"))
                
            if opts:
                self.ass_collection_dropdown.options = opts
                self.ass_collection_dropdown.value = opts[0].key
                if not is_silent:
                    self.ass_status.value = f"Сборки загружены! (Найдено: {len(opts)})"
                    self.ass_status.color = ft.Colors.GREEN_500
            else:
                self.ass_collection_dropdown.options = [ft.dropdown.Option(key="", text="Список скрыт сайтом")]
                self.ass_collection_dropdown.value = ""
                if not is_silent:
                    self.ass_status.value = "Сайт спрятал список ⬆ Используй ручной ввод"
                    self.ass_status.color = ft.Colors.ORANGE_500
                
        except Exception as ex:
            self.ass_collection_dropdown.options = [ft.dropdown.Option(key="", text="❌ Ошибка связи")]
            self.ass_collection_dropdown.value = ""
            if not is_silent:
                self.ass_status.value = f"Ошибка связи: {str(ex)}"
                self.ass_status.color = ft.Colors.RED_500
            
        if not is_silent:
            self.ass_btn.disabled = False
            self.ass_progress.visible = False
        self.page.update()

    def build_assembly_list(self, e):
        collection_input = self.ass_manual_input.value.strip()
        collection_dropdown = self.ass_collection_dropdown.value
        
        url_filter_collection = ""
        text_filter_collection = ""

        if collection_input:
            if collection_input.isdigit() and len(collection_input) >= 3:
                url_filter_collection = f"&filter_collection={collection_input}"
            else:
                text_filter_collection = collection_input.lower()
        elif collection_dropdown:
            url_filter_collection = f"&filter_collection={collection_dropdown}"
        else:
            self.ass_status.value = "❌ Выберите сборку или впишите ее вручную!"
            self.ass_status.color = ft.Colors.RED_500
            self.page.update()
            return
            
        self.ass_btn.disabled = True
        self.ass_progress.visible = True
        self.ass_status.value = "Скачивание книг для сборки..."
        self.ass_status.color = ft.Colors.CYAN_500
        self.ass_listview.controls.clear()
        self.page.update()

        if not self.admin_token and not self.perform_login(self.ass_status):
            self.ass_status.value = "❌ Ошибка логина"
            self.ass_status.color = ft.Colors.RED_500
            self.ass_btn.disabled = False
            self.ass_progress.visible = False
            self.page.update()
            return

        delivery = self.ass_delivery_dropdown.value
        shipping_map = {
            "all": "xshipping.xshipping1%2Cxshipping.xshipping3%2Cxshipping.xshipping5%2Cxshipping.xshipping6%2Crozetka_delivery%2Cmeest",
            "np": "xshipping.xshipping1%2Cxshipping.xshipping3",
            "up": "xshipping.xshipping5%2Cxshipping.xshipping6",
            "rozetka": "rozetka_delivery"
        }
        ship_filter = shipping_map.get(delivery, shipping_map["all"])
        
        limit = "300" if text_filter_collection else "200"
        
        target_url = f"https://knigoman.com.ua/admin/index.php?route=crm/order&token={self.admin_token}&filter_order_status=23&filter_limit={limit}&filter_shipping={ship_filter}{url_filter_collection}&sort=o.change_status_id+DESC%2C+o.date_added+DESC%2C+o.order_id&order=DESC"

        try:
            response = self.web_session.get(target_url, timeout=15)
            
            if "route=common/login" in response.url or "token=" not in response.url:
                if self.perform_login(self.ass_status):
                    target_url = f"https://knigoman.com.ua/admin/index.php?route=crm/order&token={self.admin_token}&filter_order_status=23&filter_limit={limit}&filter_shipping={ship_filter}{url_filter_collection}&sort=o.change_status_id+DESC%2C+o.date_added+DESC%2C+o.order_id&order=DESC"
                    response = self.web_session.get(target_url, timeout=15)
                else:
                    raise Exception("Не удалось залогиниться")

            soup = BeautifulSoup(response.text, 'html.parser')
            found_items = self.parse_items_from_soup(soup)

            if text_filter_collection:
                filtered_items = []
                for item in found_items:
                    if text_filter_collection in item.get('row_html', '').lower():
                        filtered_items.append(item)
                found_items = filtered_items

            if not found_items:
                self.ass_status.value = "Заказов в этой сборке не найдено."
                self.ass_status.color = ft.Colors.ORANGE_500
                self.ass_btn.disabled = False
                self.ass_progress.visible = False
                self.page.update()
                return

            db = self.load_databases()

            for index, item in enumerate(found_items, start=1):
                location_found, color = self.check_book_in_db(item, db)
                img_control = ft.Image(src=item["img_url"], width=60, height=80, fit='contain') if item["img_url"] else ft.Container(width=60, height=80)
                
                current_oid = item.get("order_id")
                is_last_in_order = True
                
                if index < len(found_items):
                    next_item = found_items[index]
                    if current_oid and next_item.get("order_id") == current_oid:
                        is_last_in_order = False
                
                text_column = [
                    ft.Text(f"{index}. {location_found}", weight="bold", color=color, size=15)
                ]
                if item.get("qty_text"):
                    text_column.append(ft.Text(item["qty_text"], weight="bold", color=ft.Colors.RED_500, size=16))
                
                text_column.append(ft.Text(item["display_title"], size=14))

                card_content = [
                    ft.Row([
                        img_control,
                        ft.Column(text_column, expand=True)
                    ])
                ]

                if is_last_in_order:
                    card_content.append(
                        ft.Row(
                            controls=[
                                ft.Text(f"Заказ № {current_oid}", color=ft.Colors.GREY_500, size=12, italic=True),
                                ft.FilledButton("Собрать", icon=ft.Icons.CHECK, bgcolor=ft.Colors.BLUE_GREY_800, color=ft.Colors.WHITE, height=35, on_click=lambda e, i=item: self.mark_collected(e, i))
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                        )
                    )
                
                card = ft.Container(
                    content=ft.Column(card_content),
                    padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8,
                    border=ft.Border(top=ft.border.BorderSide(2, color), bottom=ft.border.BorderSide(2, color), left=ft.border.BorderSide(2, color), right=ft.border.BorderSide(2, color))
                )
                self.ass_listview.controls.append(card)

            self.ass_status.value = f"Собрано книг: {len(found_items)}"
            self.ass_status.color = ft.Colors.GREEN_500

        except Exception as ex:
            self.ass_status.value = f"Ошибка сети: {str(ex)}"
            self.ass_status.color = ft.Colors.RED_500
            
        self.ass_btn.disabled = False
        self.ass_progress.visible = False
        self.page.update()

    # ================= ЛОГИКА ДОБАВЛЕНИЯ НА ПОЛКУ И ПОИСКА =================
    def save_place_session(self, e):
        self.silent_upload_db()

    def perform_search(self, e):
        query = self.search_input.value.strip().lower()
        self.search_listview.controls.clear()
        
        if not query:
            self.search_status.value = "Введите запрос"
            self.page.update()
            return
            
        self.search_btn.disabled = True
        self.search_progress.visible = True
        self.search_status.value = "Поиск..."
        self.page.update()

        query_norm = ' '.join(re.sub(r'[^\w\s]', '', query).split())
        db = self.load_databases()
        found_books = []
        for location, books in db.items():
            for title, info in books.items():
                barcode = str(info.get("Штрихкод", "")).strip().lower()
                balka = str(info.get("Balka code", "")).strip().lower()
                title_norm = re.sub(r'[^\w\s]', '', title.lower())
                if query in title.lower() or (query_norm and query_norm in title_norm) or query in barcode or query in balka:
                    found_books.append({"title": title, "balka": balka, "location": location})

        if not found_books:
            self.search_status.value = "Ничего не найдено."
        else:
            self.search_status.value = f"Найдено: {len(found_books)}"
            for book in found_books:
                card = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Column([
                                ft.Text(book['title'], weight="bold", size=15),
                                ft.Text(book['location'], color=ft.Colors.CYAN, size=13),
                                ft.Text(f"Balka: {book['balka']}", color=ft.Colors.ORANGE, size=13)
                            ], expand=True),
                            
                            ft.IconButton(
                                icon=ft.Icons.DELETE_OUTLINE, 
                                icon_color=ft.Colors.RED_500,
                                tooltip="Удалить книгу",
                                on_click=lambda e, b=book: self.delete_book_from_cell(b)
                            )
                        ])
                    ]),
                    padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8
                )
                self.search_listview.controls.append(card)
        
        self.search_btn.disabled = False
        self.search_progress.visible = False
        self.page.update()

    # --- ПОИСК МЕСТА ---
    def clear_place_list(self, e):
        self.place_listview.controls.clear()
        self.scanned_items.clear()
        self.place_input.value = ""
        self.place_save_btn.visible = False
        self.page.update()

    def perform_place_search(self, e):
        query = self.place_input.value.strip().lower()
        if not query:
            self.page.update()
            return

        query_norm = ' '.join(re.sub(r'[^\w\s]', '', query).split())
        db = self.load_databases()
        found_books = []
        
        for location, books in db.items():
            for title, info in books.items():
                barcode = str(info.get("Штрихкод", "")).strip().lower()
                balka = str(info.get("Balka code", "")).strip().lower()
                title_norm = re.sub(r'[^\w\s]', '', title.lower())
                if query in title.lower() or (query_norm and query_norm in title_norm) or query in barcode or query in balka:
                    found_books.append({"title": title, "barcode": barcode, "balka": balka, "location": location})

        if not found_books:
            card = ft.Container(content=ft.Text(f"❌ '{query}' не найдена в базах", color=ft.Colors.RED_500, size=16, weight="bold"), padding=15, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8)
            self.place_listview.controls.insert(0, card)
        else:
            is_duplicate = False
            for book in found_books:
                unique_key = book['barcode'] if book['barcode'] else book['title']
                if unique_key in self.scanned_items: is_duplicate = True
                else: self.scanned_items.add(unique_key)

            for book in found_books:
                card = ft.Container(
                    content=ft.Column([
                        ft.Text(f"📍 {book['location']}", color=ft.Colors.GREEN_500, size=24, weight="bold"),
                        ft.Text(book['title'], weight="bold", size=15),
                        ft.Text(f"Штрихкод: {book['barcode']} | Balka: {book['balka']}", color=ft.Colors.GREY_400, size=13)
                    ]), padding=15, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8)
                self.place_listview.controls.insert(0, card)

            if is_duplicate:
                dup_msg = ft.Container(content=ft.Text(f"⚠️ ПОВТОР: Эта книга уже была отсканирована!", color=ft.Colors.ORANGE_500, size=16, weight="bold"), padding=10, border=ft.Border(top=ft.border.BorderSide(2, ft.Colors.ORANGE_500), bottom=ft.border.BorderSide(2, ft.Colors.ORANGE_500), left=ft.border.BorderSide(2, ft.Colors.ORANGE_500), right=ft.border.BorderSide(2, ft.Colors.ORANGE_500)), border_radius=8)
                self.place_listview.controls.insert(0, dup_msg)
        
        self.place_save_btn.visible = True
        self.place_input.value = "" 
        self.page.update()

def main(page: ft.Page):
    app = InventoryMobileApp(page)

if __name__ == "__main__":
    ft.app(target=main)