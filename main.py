import flet as ft
import os
import sqlite3
import requests
import re
import ast
import threading
import time
from datetime import datetime
from bs4 import BeautifulSoup

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
        
        # Память для отсканированных книг в расстановке
        self.scanned_items = set()

        self.build_ui()

        # Загрузка и применение сохраненной темы
        saved_theme = self.load_theme()
        self.theme_dropdown.value = saved_theme
        self.apply_theme(saved_theme)

        self.auto_sync_thread = threading.Thread(target=self.auto_update_loop, daemon=True)
        self.auto_sync_thread.start()

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

    def auto_update_loop(self):
        while True:
            time.sleep(1800)
            self.silent_download_db()

    # --- DROPBOX: ТИХОЕ ОБНОВЛЕНИЕ ---
    def silent_download_db(self):
        saved_db_url = ""
        try:
            if os.path.exists("settings.txt"):
                with open("settings.txt", "r", encoding="utf-8") as f:
                    saved_db_url = f.read().strip()
        except: pass

        if not saved_db_url: return
        
        dropbox_link = saved_db_url
        if "?dl=0" in dropbox_link:
            dropbox_link = dropbox_link.replace("?dl=0", "?dl=1")
        elif "?dl=1" not in dropbox_link:
            dropbox_link += "?dl=1"

        try:
            response = requests.get(dropbox_link, timeout=30)
            if response.status_code == 200:
                db_path = os.path.join(DB_FOLDER, "inventory.db")
                with open(db_path, 'wb') as f:
                    f.write(response.content)
                now = datetime.now().strftime("%H:%M")
                self.db_status.value = f"✅ База обновлена в {now}!"
                self.db_status.color = ft.Colors.GREEN_700
                self.page.update()
        except: pass

    # --- DROPBOX: РУЧНОЕ СКАЧИВАНИЕ ---
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

        dropbox_link = url_input
        if "?dl=0" in dropbox_link:
            dropbox_link = dropbox_link.replace("?dl=0", "?dl=1")
        elif "?dl=1" not in dropbox_link:
            dropbox_link += "?dl=1"

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

    # --- SQLITE ЧТЕНИЕ ---
    def load_databases(self):
        master_db = {}
        db_path = os.path.join(DB_FOLDER, "inventory.db")
        
        if not os.path.exists(db_path):
            print("База inventory.db не найдена!")
            return master_db
            
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, location FROM books")
            books = cursor.fetchall()
            cursor.execute("SELECT book_id, code_value, code_type FROM barcodes")
            barcodes = cursor.fetchall()
            
            book_codes = {}
            for b_id, val, ctype in barcodes:
                if b_id not in book_codes:
                    book_codes[b_id] = {"Штрихкод": "", "Balka code": ""}
                if ctype == 'barcode':
                    book_codes[b_id]["Штрихкод"] = val
                elif ctype == 'balka':
                    book_codes[b_id]["Balka code"] = val
            
            for b_id, title, loc in books:
                if loc not in master_db:
                    master_db[loc] = {}
                master_db[loc][title] = book_codes.get(b_id, {"Штрихкод": "", "Balka code": ""})
                
            conn.close()
        except Exception as e:
            print(f"Ошибка при чтении SQLite: {e}")
            
        return master_db

    # --- ПОИСК МЕСТА ---
    def clear_place_list(self, e):
        self.place_listview.controls.clear()
        self.scanned_items.clear()
        self.place_input.value = ""
        self.page.update()

    def perform_place_search(self, e):
        query = self.place_input.value.strip().lower()
        if not query:
            self.page.update()
            return

        query_norm = re.sub(r'[^\w\s]', '', query)
        query_norm = ' '.join(query_norm.split())

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
            card = ft.Container(
                content=ft.Text(f"❌ '{query}' не найдена в базах", color=ft.Colors.RED_500, size=16, weight="bold"),
                padding=15, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8
            )
            self.place_listview.controls.insert(0, card)
        else:
            is_duplicate = False
            for book in found_books:
                unique_key = book['barcode'] if book['barcode'] else book['title']
                if unique_key in self.scanned_items:
                    is_duplicate = True
                else:
                    self.scanned_items.add(unique_key)

            for book in found_books:
                card = ft.Container(
                    content=ft.Column([
                        ft.Text(f"📍 {book['location']}", color=ft.Colors.GREEN_500, size=24, weight="bold"),
                        ft.Text(book['title'], weight="bold", size=15),
                        ft.Text(f"Штрихкод: {book['barcode']} | Balka: {book['balka']}", color=ft.Colors.GREY_400, size=13)
                    ]),
                    padding=15, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8
                )
                self.place_listview.controls.insert(0, card)

            if is_duplicate:
                dup_msg = ft.Container(
                    content=ft.Text(f"⚠️ ПОВТОР: Эта книга уже была отсканирована!", color=ft.Colors.ORANGE_500, size=16, weight="bold"),
                    padding=10, 
                    border=ft.Border(
                        top=ft.border.BorderSide(2, ft.Colors.ORANGE_500), 
                        bottom=ft.border.BorderSide(2, ft.Colors.ORANGE_500), 
                        left=ft.border.BorderSide(2, ft.Colors.ORANGE_500), 
                        right=ft.border.BorderSide(2, ft.Colors.ORANGE_500)
                    ), 
                    border_radius=8
                )
                self.place_listview.controls.insert(0, dup_msg)
        
        self.place_input.value = "" 
        self.page.update()

    def build_ui(self):
        saved_db_url = ""
        try:
            if os.path.exists("settings.txt"):
                with open("settings.txt", "r", encoding="utf-8") as f:
                    saved_db_url = f.read().strip()
        except: pass

        # === ВКЛАДКА СБОРКИ ===
        self.ass_url_input = ft.TextField(label="Ссылка на заказ", hint_text="Вставьте ссылку...", expand=True)
        self.ass_btn = ft.FilledButton("Собрать", on_click=self.build_assembly_list, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE)
        self.ass_status = ft.Text("Ожидание...", color=ft.Colors.ORANGE_700)
        self.ass_progress = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)
        self.ass_listview = ft.ListView(expand=True, spacing=10, padding=10)
        
        self.view_assembly = ft.Column([
            ft.Container(
                content=ft.Column([
                    self.ass_url_input, 
                    self.ass_btn, 
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
            # Убран автофокус, чтобы клавиатура не вылезала постоянно
            on_submit=self.perform_place_search 
        )
        
        self.place_clear_btn = ft.IconButton(
            icon=ft.Icons.DELETE_SWEEP, 
            icon_color=ft.Colors.RED_400, 
            on_click=self.clear_place_list, 
            tooltip="Очистить список"
        )
        
        self.place_listview = ft.ListView(expand=True, spacing=10, padding=10)

        self.view_place = ft.Column([
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("Куда поставить книгу?", weight="bold", size=18),
                        ft.Container(expand=True), 
                        self.place_clear_btn
                    ]),
                    ft.Row([self.place_input])
                ]),
                padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=10
            ),
            self.place_listview
        ], expand=True, visible=False)

        # === ВКЛАДКА ПОИСКА ===
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
                ft.NavigationBarDestination(icon=ft.Icons.FOLDER, label="База"),
                ft.NavigationBarDestination(icon=ft.Icons.SETTINGS, label="Настройки"),
            ],
            on_change=self.on_nav_change,
            selected_index=3
        )

        self.page.add(ft.SafeArea(content=self.main_container, expand=True))

    def on_nav_change(self, e):
        idx = e.control.selected_index
        self.view_assembly.visible = (idx == 0)
        self.view_place.visible = (idx == 1)
        self.view_search.visible = (idx == 2)
        self.view_db.visible = (idx == 3)
        self.view_settings.visible = (idx == 4)
        
        self.page.update()

    # --- УМНЫЙ ПОИСК ---
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
            if matches / len(s_significant) >= 0.7:
                return True
                
        return False

    def perform_login(self, status_label=None):
        if status_label:
            status_label.value = "Авторизация..."
            status_label.color = ft.Colors.CYAN
            self.page.update()
        
        login_url = "https://knigoman.com.ua/admin/index.php?route=common/login"
        self.web_session.headers.update({'User-Agent': 'Mozilla/5.0'})
        try:
            self.web_session.get(login_url, timeout=10)
            payload = {'username': self.auto_user, 'password': self.auto_pass, 'redirect': 'https://knigoman.com.ua/admin/index.php?route=crm/order'}
            response = self.web_session.post(login_url, data=payload, timeout=15)
            if 'token=' in response.url:
                self.admin_token = re.search(r'token=([^&]+)', response.url).group(1)
                if status_label:
                    status_label.value = "Успешный вход!"
                    status_label.color = ft.Colors.GREEN
                    self.page.update()
                return True
            return False
        except Exception as e:
            return False

    def clean_book_specs(self, full_text, title):
        text = full_text.replace(title, "", 1).strip()
        balka_match = re.search(r'балка\s*[:-]?\s*([a-zA-Z0-9а-яА-Я]+)', text.lower())
        balka_text = f"Балка: {balka_match.group(1).upper()}" if balka_match else ""
        text_lower = text.lower()
        cut_words = ['шинко', 'застела', 'резерв']
        for word in cut_words:
            idx = text_lower.find(word)
            if idx != -1:
                text = text[:idx]
                text_lower = text_lower[:idx] 
        good_keywords = ['твердая', 'мягкая', 'палитурка', 'обложка', 'бумага', 'цвет', 'покет', 'а5', 'увеличенный', 'формат', 'укр', 'рус', 'рос']
        words = text.replace('|', ' ').split()
        temp_phrase = []
        for word in words:
            w_lower = word.lower()
            if re.match(r'^\(?\d+([.,]\d+)?\)?$', w_lower): 
                continue
            if 'балка' in w_lower or (balka_match and balka_match.group(1).lower() in w_lower):
                continue
            if any(junk in w_lower for junk in ['грн', 'id:', 'артикул', 'isbn', 'шт.', 'кол-во', 'модель']):
                continue
            if any(good in w_lower for good in good_keywords) or len(word) > 3:
                 temp_phrase.append(word)
        cleaned = " ".join(temp_phrase)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip(' -.,|;()') 
        final_result = []
        if cleaned:
            final_result.append(cleaned)
        if balka_text:
            final_result.append(balka_text)
        if final_result:
            return f" ({' | '.join(final_result)})"
        return ""

    def parse_items_from_soup(self, soup, current_url=""):
        found_items = []
        global_order_id = ""
        m_url = re.search(r'order_id=(\d+)', current_url)
        if m_url:
            global_order_id = m_url.group(1)

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
                        if qty_match:
                            qty_text = f"🔥 НУЖНО {qty_match.group(1)} ШТ. 🔥"
                
                if not qty_text:
                    qty_match = re.search(r'!\s*(\d+)\s*шт', text_content.lower())
                    if qty_match:
                        qty_text = f"🔥 НУЖНО {qty_match.group(1)} ШТ. 🔥"

                clean_specs = self.clean_book_specs(text_content, title)
                
                img_tag = None
                if text_container:
                    img_tag = text_container.find('img')
                    if not img_tag:
                        prev = text_container.find_previous_sibling()
                        if prev: img_tag = prev if prev.name == 'img' else prev.find('img')
                
                img_url = img_tag.get('src') if img_tag else None
                
                order_id = global_order_id
                order_product_id = ""
                status_id = "25"

                row = a.find_parent('tr')
                if row:
                    row_html = str(row)
                    m_opid = re.search(r'collectionToAssembled\([^,]+,\s*(\d+)\)', row_html)
                    if m_opid:
                        order_product_id = m_opid.group(1)
                        
                    m_stat = re.search(r'data-status-id="(\d+)"', row_html)
                    if m_stat:
                        status_id = m_stat.group(1)

                    if not order_id:
                        order_input = row.find('input', {'name': re.compile(r'order_id')})
                        if order_input: order_id = order_input.get('value', '')
                        if not order_id:
                            m_oid = re.search(r'order_id=(\d+)', row_html)
                            if m_oid: order_id = m_oid.group(1)

                display_info = f"{title}{clean_specs}"
                
                found_items.append({
                    "title": title, 
                    "display_title": display_info, 
                    "full_text": text_content, 
                    "img_url": img_url,
                    "order_product_id": order_product_id,
                    "status_id": status_id,
                    "order_id": order_id,
                    "qty_text": qty_text
                })
        return found_items

    def mark_collected(self, e, item):
        btn = e.control
        btn.disabled = True
        btn.text = "⏳"
        btn.update()

        o_id = item.get("order_id")
        op_id = item.get("order_product_id")
        s_id = item.get("status_id", "25")

        if not op_id or not o_id:
            btn.text = "❌"
            btn.update()
            return

        def send_request():
            ajax_url = "https://knigoman.com.ua/index.php?route=crm/crm_api/changeField"
            payload = {'order_id': str(o_id), 'field': 'order_status_id', 'field_name': 'Статус заказа', 'value': str(s_id), 'custom_field': 'false', 'user_id': '36'}
            headers = {'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8', 'Accept': 'application/json, text/javascript, */*; q=0.01', 'Cookie': '; '.join([f'{c.name}={c.value}' for c in self.web_session.cookies])}
            return self.web_session.post(ajax_url, data=payload, headers=headers, timeout=10)

        try:
            if not self.admin_token: self.perform_login()
            response = send_request()
            
            if "login" in response.url.lower() or response.status_code == 403:
                if self.perform_login(): response = send_request() 
                else:
                    btn.text = "❌"
                    btn.update()
                    return

            if response.status_code == 200:
                btn.text = "✅"
                btn.bgcolor = ft.Colors.GREEN_700
            else:
                btn.text = "❌"
                btn.bgcolor = ft.Colors.RED_700
        except Exception:
            btn.text = "❌"
            btn.bgcolor = ft.Colors.RED_700

        btn.update()

    # --- УМНАЯ ПРОВЕРКА КНИГ НА ПОЛКЕ ---
    def check_book_in_db(self, item, db):
        locations = []
        site_full_text = item.get("full_text", "").lower()
        
        for loc, books in db.items():
            for db_title, info in books.items():
                db_balka = str(info.get("Balka code", "")).strip().lower()
                
                title_matched = self.smart_match(item["title"], db_title)
                
                balka_matched = False
                if db_balka and len(db_balka) > 3 and db_balka in site_full_text:
                    balka_matched = True
                    
                if title_matched or balka_matched:
                    if loc not in locations:
                        locations.append(loc)
        
        if locations:
            joined_locations = " | ".join(locations)
            return joined_locations, ft.Colors.GREEN_700
            
        return "Нет в базах", ft.Colors.RED_400

    def build_assembly_list(self, e):
        url = self.ass_url_input.value.strip()
        if not url: return
        
        self.ass_btn.disabled = True
        self.ass_progress.visible = True
        self.ass_status.value = "Загрузка..."
        self.ass_listview.controls.clear()
        self.page.update()
        
        if not self.admin_token and not self.perform_login(self.ass_status):
            self.ass_btn.disabled = False
            self.ass_progress.visible = False
            self.page.update()
            return

        url_with_token = re.sub(r'token=[^&]+', f'token={self.admin_token}', url)

        try:
            response = self.web_session.get(url_with_token, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            found_items = self.parse_items_from_soup(soup, current_url=url_with_token)

            if not found_items:
                self.ass_status.value = "Пусто."
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
                    next_oid = next_item.get("order_id")
                    if current_oid and next_oid == current_oid:
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
                                ft.FilledButton(
                                    "Собрать",
                                    icon=ft.Icons.CHECK,
                                    bgcolor=ft.Colors.BLUE_GREY_800,
                                    color=ft.Colors.WHITE,
                                    height=35,
                                    on_click=lambda e, i=item: self.mark_collected(e, i)
                                )
                            ],
                            alignment=ft.MainAxisAlignment.END
                        )
                    )
                
                card = ft.Container(
                    content=ft.Column(card_content),
                    padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8,
                    border=ft.Border(top=ft.border.BorderSide(2, color), bottom=ft.border.BorderSide(2, color), left=ft.border.BorderSide(2, color), right=ft.border.BorderSide(2, color))
                )
                self.ass_listview.controls.append(card)

            self.ass_status.value = f"Собрано: {len(found_items)}"
            self.ass_status.color = ft.Colors.GREEN

        except Exception as ex:
            self.ass_status.value = f"Ошибка: {str(ex)}"
            self.ass_status.color = ft.Colors.RED
            
        self.ass_btn.disabled = False
        self.ass_progress.visible = False
        self.page.update()

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

        query_norm = re.sub(r'[^\w\s]', '', query)
        query_norm = ' '.join(query_norm.split())

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
                        ft.Text(book['title'], weight="bold", size=15),
                        ft.Text(book['location'], color=ft.Colors.CYAN, size=13),
                        ft.Text(f"Balka: {book['balka']}", color=ft.Colors.ORANGE, size=13)
                    ]),
                    padding=10, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8
                )
                self.search_listview.controls.append(card)
        
        self.search_btn.disabled = False
        self.search_progress.visible = False
        self.page.update()

def main(page: ft.Page):
    app = InventoryMobileApp(page)

if __name__ == "__main__":
    ft.app(target=main)