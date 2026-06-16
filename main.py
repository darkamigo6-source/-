import asyncio
import io
import calendar
import logging
import json
import re
import traceback
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.session.aiohttp import AiohttpSession
import gspread
from google.oauth2.service_account import Credentials
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.utils import simpleSplit
import aiohttp

TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"
ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
ID_PERSONAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
ID_PRICES = "1vbYaXXzQNsptih94WaOkd_6tkoGFbuJrSKOVAbgN1IA"
ID_SALARY = "1xD3DKtZF9dJ3FGvB7FwWMgHz6uwgKa7irKo4l9iaL9I"
ID_NESTANDART = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
NESTANDART_SHEET_NAME = "Nestandart"
ID_SALARY_MANUAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
SALARY_MANUAL_SHEET = "SalaryManual"
ADMIN_IDS = {766046065, 1801066113, 441617458}
FONT_NAME = "Arial"

# === ГОД ДЛЯ ОТЧЁТОВ (поменяй если нужно) ===
REPORT_YEAR = 2026

FIXED_OZON_PRICES = {
    "МЕБЕЛЬПАК СТОЛ ЖУРНАЛЬНЫЙ БЕЛЫЙ": 3800,
    "МЕБЕЛЬПАК СТОЛ ЖУРНАЛЬНЫЙ СОНОМА": 4110,
    "МЕБЕЛЬПАК ТУМБА ПРИКРОВАТНАЯ НАПОЛЬНАЯ С ВЫДВИЖНЫМ БЕЛАЯ": 2700,
    "МЕБЕЛЬПАК ТУМБА ПРИКРОВАТНАЯ НАПОЛЬНАЯ С ВЫДВИЖНЫМ СОНОМА": 2700,
    "МЕБЕЛЬПАК ТУМБА ПРИКРОВАТНАЯ НАПОЛЬНАЯ С ВЫДВИЖНЫМ": 2700,
    "ОЗОН СТОЛЕШНИЦА ДЛЯ РЕСЕПШЕНА УНИВЕРСАЛЬНАЯ": 788,
}

EXCLUDED_FINANCE_NAMES_RAW = {
    "ПРАКТИК Ключница KEY-100", "ПРАКТИК Ключница KEY-20", "ПРАКТИК Ключница KEY-40",
    "ПРАКТИК Ключница KEY-60", "ПРАКТИК Почтовый ящик PB-4C.KL RВ",
    "ПРАКТИК Сейф оружейный ЧИРОК 1015", "ПРАКТИК Сейф оружейный ЧИРОК 1018",
    "ПРАКТИК Стеллаж металлический 20010040см",
    "B5_Новый_Брендбук Накладка на Стол менеджера",
    "B5_Новый_Брендбук Накладка на Большой стол проверки товаров",
    "B5_Новый_Брендбук Накладка на Стол выдачи на три ячейки",
    "B5_Новый_Брендбук Накладка на Маленький стол проверки товаров",
    "B5_Новый_Брендбук Накладка на стол выдачи на две ячейки",
    "OZN3543224719 ВБ_Новый_Брендбук Накладка на Большой стол проверки товаров",
    "OZN3543231747 ВБ_Новый_Брендбук Накладка на Маленький стол проверки товаров",
    "OZN3539362120 ВБ_Новый_Брендбук Накладка на стол выдачи на две ячейки",
    "OZN3539374066 ВБ_Новый_Брендбук Накладка на Стол выдачи на три ячейки",
    "OZN3539340805 ВБ_Новый_Брендбук Накладка на Стол менеджера",
    "ПРАКТИК Оружейный сейф AIKO TT-28 с ключевым замком",
    "ПРАКТИК Сейф оружейный пистолетный AIKO TT-28 EL с трейзером и электронным кодовым замком",
    "ПРАКТИК Стеллаж для рассады, склада, сада оцинкованный Практик 75*75*30см, 3 полки, ES 75KD",
    "ПРАКТИК Стеллаж металлический 200*100*40см",
    "ПРАКТИК AIKO Т-140 EL", "ПРАКТИК AIKO Т-140 KL",
    "ПРАКТИК AIKO Т-170 EL", "ПРАКТИК AIKO Т-200 EL", "ПРАКТИК AIKO Т-200 KL",
    "ПРАКТИК AIKO Т-23 EL", "ПРАКТИК AIKO Т-230 EL", "ПРАКТИК AIKO Т-230 KL",
    "ПРАКТИК AIKO Т-250 EL", "ПРАКТИК AIKO Т-250 KL",
    "ПРАКТИК AIKO Т-28", "ПРАКТИК AIKO Т-28 EL",
    "ПРАКТИК AIKO Т-280 EL", "ПРАКТИК AIKO Т-280 KL",
    "ПРАКТИК AIKO SL-125/2Т", "ПРАКТИК AIKO SL-125Т",
    "ПРАКТИК AIKO SL-32", "ПРАКТИК AIKO SL-32T",
    "ПРАКТИК AIKO SL-65Т", "ПРАКТИК AIKO SL-87Т",
    "ПРАКТИК AIKO T-170 KL", "ПРАКТИК AIKO TM-25",
    "ПРАКТИК AIKO TT-170", "ПРАКТИК AIKO TT-200 EL", "ПРАКТИК AIKO TT-23",
    "ПРАКТИК TT-170 EL", "ПРАКТИК TT-200", "ПРАКТИК TT-23 EL",
    "ПРАКТИК VALBERG FRS-32 EL", "ПРАКТИК VALBERG FRS-36 KL",
    "Накладка на Стол менеджера",
    "Накладка на Большой стол проверки товаров",
    "Накладка на Стол выдачи на три ячейки",
    "Накладка на Маленький стол проверки товаров",
    "Накладка на стол выдачи на две ячейки",
}

EXCLUDED_SUBSTRINGS = [
    "ПРАКТИК",
    "НАКЛАДКА НА СТОЛ МЕНЕДЖЕРА",
    "НАКЛАДКА НА БОЛЬШОЙ СТОЛ ПРОВЕРКИ",
    "НАКЛАДКА НА СТОЛ ВЫДАЧИ НА ТРИ",
    "НАКЛАДКА НА МАЛЕНЬКИЙ СТОЛ ПРОВЕРКИ",
    "НАКЛАДКА НА СТОЛ ВЫДАЧИ НА ДВЕ",
    "КЛЮЧНИЦА KEY-",
    "СЕЙФ ОРУЖЕЙНЫЙ",
    "AIKO SL-",
    "AIKO TT-",
    "AIKO TM-",
    "AIKO Т-",
    "AIKO T-",
    "VALBERG FRS-",
    "ПОЧТОВЫЙ ЯЩИК PB-",
]

COLOR_VARIATIONS = [
    "белый", "белая", "белое", "белые",
    "сонома", "дуб сонома",
    "венге", "дуб венге",
    "черный", "черная", "черное", "черные",
    "серый", "серая", "серое", "серые",
    "бежевый", "бежевая", "бежевое",
    "орех", "ореховый",
    "ясень", "ясень шимо",
    "светлый", "светлая", "темный", "темная",
]

PRICE_SHEETS_CONFIG = {
    "Цены для Озон ПВЗ": {"article_col": 0, "price_col": 57, "name_col": 1},
    "Мебельддома": {"article_col": 0, "price_col": 2, "name_col": 1},
    "Новый ББ ВБ": {"article_col": 0, "price_col": 2, "name_col": 1}
}

PROXY_URL = "socks5://nZFaKS:E8CLs4@168.0.215.51:9907"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

dp = Dispatcher(storage=MemoryStorage())

class ReportStates(StatesGroup):
    rep_mode = State()
    start_date = State()
    waiting_ozon_price = State()
    pending_items = State()
    collected_prices = State()
    current_item_index = State()
    report_data = State()

class SalaryStates(StatesGroup):
    waiting_salary_price = State()

def get_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('creds.json', scopes=scopes)
    return gspread.authorize(creds)

def parse_any_date(date_str):
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except:
        return None

def normalize_string(s):
    if not s:
        return ""
    return str(s).strip().upper()

def parse_price(price_str):
    if not price_str:
        return 0.0
    try:
        clean = str(price_str).strip()
        clean = clean.replace(',', '.').replace(' ', '').replace('₽', '').replace('р', '').replace('руб', '')
        clean = re.sub(r'[^\d.]', '', clean)
        if clean:
            return float(clean)
    except:
        pass
    return 0.0

def get_base_product_name(name):
    name_lower = name.lower().strip()
    for color in COLOR_VARIATIONS:
        if name_lower.endswith(" " + color):
            name_lower = name_lower[:-len(color)-1].strip()
        name_lower = name_lower.replace(" " + color + " ", " ")
    return name_lower.strip()

EXCLUDED_NORMALIZED = {normalize_string(name) for name in EXCLUDED_FINANCE_NAMES_RAW}

def is_excluded(product_name):
    if not product_name:
        return False
    name_norm = normalize_string(product_name)
    if name_norm in EXCLUDED_NORMALIZED:
        return True
    for sub in EXCLUDED_SUBSTRINGS:
        if sub in name_norm:
            return True
    return False


def save_to_salary_manual(product_name, price):
    gc = get_client()
    try:
        sh = gc.open_by_key(ID_SALARY_MANUAL)

        try:
            sheet = sh.worksheet(SALARY_MANUAL_SHEET)
        except:
            sheet = sh.add_worksheet(title=SALARY_MANUAL_SHEET, rows=1000, cols=2)
            sheet.update_cell(1, 1, "Название")
            sheet.update_cell(1, 2, "Цена")

        rows = sheet.get_all_values()
        name_norm = normalize_string(product_name)

        for i, row in enumerate(rows[1:], start=2):
            if normalize_string(row[0]) == name_norm:
                sheet.update_cell(i, 2, price)
                return

        sheet.append_row([product_name, price])

    except Exception as e:
        logging.error(f"Ошибка записи зарплатной цены: {e}")


def load_salary_manual_prices():
    gc = get_client()
    prices = {}

    try:
        sh = gc.open_by_key(ID_SALARY_MANUAL)
        sheet = sh.worksheet(SALARY_MANUAL_SHEET)
        rows = sheet.get_all_values()

        for row in rows[1:]:
            if len(row) >= 2:
                name = normalize_string(row[0])
                price = parse_price(row[1])
                if price > 0:
                    prices[name] = price

        return prices

    except:
        return {}
def calculate_inventory(inventory, price_dict):
    all_items = []
    total_qty = 0
    total_sum = 0
    items_without_price = []

    for v in inventory.values():
        qty = v['p1'] + v['p2']
        if qty <= 0:
            continue

        name = v['name']
        name_key = normalize_string(name)

        price = price_dict.get(name_key, 0)   # ✅ ТОЛЬКО из словаря

        total_qty += qty

        if price > 0:
            item_total = qty * price
            total_sum += item_total
        else:
            item_total = 0
            items_without_price.append({
                "name": name,
                "qty": qty
            })

        all_items.append({
            "name": name,
            "qty": qty,
            "price": price,
            "total": item_total
        })

    return all_items, total_qty, total_sum, items_without_price
def create_beautiful_pdf(all_items, total_qty, total_sum, period_text):
    try:
        buffer = io.BytesIO()
        pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
        c = canvas.Canvas(buffer, pagesize=A4)

        w, h = A4
        margin = 35
        y = h - 50

        # ===== ЗАГОЛОВОК =====
        c.setFont(FONT_NAME, 14)
        c.drawCentredString(w / 2, y, f"ОТЧЕТ: {period_text}")
        y -= 30

        # ===== БЛОК ИТОГОВ =====
        c.setFillColor(colors.HexColor("#E8F5E9"))
        c.rect(margin, y - 35, w - margin * 2, 40, fill=1, stroke=0)

        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 11)
        c.drawString(margin + 10, y - 15, f"Всего изделий: {int(total_qty)}")
        c.drawString(margin + 10, y - 30, f"Общая сумма: {total_sum:,.0f} руб.")

        y -= 60

        # ===== ШАПКА ТАБЛИЦЫ =====
        c.setFillColor(colors.HexColor("#E3F2FD"))
        c.rect(margin, y - 15, w - margin * 2, 18, fill=1, stroke=0)

        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 8)

        col_x = [
            margin + 5,
            margin + 300,
            margin + 360,
            margin + 440
        ]

        c.drawString(col_x[0], y - 10, "Изделие")
        c.drawString(col_x[1], y - 10, "Кол-во")
        c.drawString(col_x[2], y - 10, "Цена")
        c.drawString(col_x[3], y - 10, "Сумма")

        y -= 25
        c.setFont(FONT_NAME, 7)

        # ===== ТЕЛО ТАБЛИЦЫ =====
        for item in all_items:

            if y < 70:
                c.showPage()
                c.setFont(FONT_NAME, 7)
                y = h - 50

            name = item["name"]
            qty = int(item["qty"])
            price = item["price"]
            total = item["total"]

            name_short = name[:45] + "..." if len(name) > 45 else name

            c.setStrokeColor(colors.HexColor("#E0E0E0"))
            c.line(margin, y - 3, w - margin, y - 3)

            c.drawString(col_x[0], y, name_short)
            c.drawString(col_x[1], y, f"{qty}")
            c.drawString(col_x[2], y, f"{price:,.0f}" if price > 0 else "---")
            c.drawString(col_x[3], y, f"{total:,.0f}" if total > 0 else "-")

            y -= 12

        # ===== НИЖНИЙ ИТОГ =====
        c.setFillColor(colors.HexColor("#C8E6C9"))
        c.rect(margin, 30, w - margin * 2, 25, fill=1, stroke=0)

        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawCentredString(
            w / 2,
            40,
            f"ИТОГО: {total_sum:,.0f} руб. | Изделий: {int(total_qty)}"
        )

        c.save()
        buffer.seek(0)

        return buffer

    except Exception as e:
        logging.error(f"Ошибка красивого PDF: {e}")
        raise
def save_to_nestandart(product_name, price):
    gc = get_client()
    try:
        sh = gc.open_by_key(ID_NESTANDART)
        try:
            sheet = sh.worksheet(NESTANDART_SHEET_NAME)
        except:
            sheet = sh.add_worksheet(title=NESTANDART_SHEET_NAME, rows=1000, cols=2)
            sheet.update_cell(1, 1, "Название")
            sheet.update_cell(1, 2, "Цена")
        rows = sheet.get_all_values()
        name_norm = normalize_string(product_name)
        for i, row in enumerate(rows[1:], start=2):
            if len(row) >= 1 and normalize_string(row[0]) == name_norm:
                sheet.update_cell(i, 2, price)
                logging.info(f"Обновлена цена в Nestandart: {product_name} = {price}")
                return True
        sheet.append_row([product_name, price])
        logging.info(f"Добавлено в Nestandart: {product_name} = {price}")
        return True
    except Exception as e:
        logging.error(f"Ошибка записи в Nestandart: {e}")
        return False

def load_salary_prices():
    gc = get_client()
    salary_prices = {}
    try:
        sh = gc.open_by_key(ID_SALARY)
        sheet = sh.sheet1
        rows = sheet.get_all_values()
        for row in rows[1:]:
            if len(row) >= 2:
                name = str(row[0]).strip()
                price = parse_price(row[1])
                if name and price > 0:
                    salary_prices[normalize_string(name)] = {"name": name, "price": price}
        logging.info(f"Загружено {len(salary_prices)} цен для зарплаты")
        return salary_prices
    except Exception as e:
        logging.error(f"Ошибка загрузки цен зарплаты: {e}")
        return {}

def load_nestandart_prices():
    gc = get_client()
    nestandart_prices = {}
    try:
        sh = gc.open_by_key(ID_NESTANDART)
        try:
            sheet = sh.worksheet(NESTANDART_SHEET_NAME)
        except:
            logging.warning(f"Лист '{NESTANDART_SHEET_NAME}' не найден")
            return {}
        rows = sheet.get_all_values()
        for row in rows[1:]:
            if len(row) >= 2:
                name = str(row[0]).strip()
                price = parse_price(row[1])
                if name and price > 0:
                    nestandart_prices[normalize_string(name)] = {"name": name, "price": price}
        logging.info(f"Загружено {len(nestandart_prices)} нестандартных цен")
        return nestandart_prices
    except Exception as e:
        logging.error(f"Ошибка загрузки нестандартных цен: {e}")
        return {}

def get_salary_price_for_product(product_name, salary_prices, nestandart_prices):
    if not product_name:
        return 0

    name_key = normalize_string(product_name)

    # точное совпадение
    if name_key in salary_prices:
        return salary_prices[name_key]["price"]

    if name_key in nestandart_prices:
        return nestandart_prices[name_key]["price"]

    # совпадение без цвета
    base_name = get_base_product_name(product_name)
    base_key = normalize_string(base_name)

    if base_key in salary_prices:
        return salary_prices[base_key]["price"]

    if base_key in nestandart_prices:
        return nestandart_prices[base_key]["price"]

    return 0

def load_ozon_prices_from_sheet():
    gc = get_client()
    prices_data = {}
    name_to_prices = {}
    try:
        sh = gc.open_by_key(ID_PRICES)
        for sheet_name, config in PRICE_SHEETS_CONFIG.items():
            logging.info(f"Загружаю: {sheet_name}")
            article_col = config["article_col"]
            price_col = config["price_col"]
            name_col = config["name_col"]
            try:
                sheet = sh.worksheet(sheet_name)
                rows = sheet.get_all_values()
                if len(rows) < 2:
                    continue
                count_before = len(prices_data)
                for row in rows[1:]:
                    if len(row) <= article_col:
                        continue
                    article = str(row[article_col]).strip()
                    product_name = str(row[name_col]).strip() if len(row) > name_col else ""
                    if not article:
                        continue
                    price = 0.0
                    if len(row) > price_col:
                        price = parse_price(row[price_col])
                    if price > 0:
                        prices_data[article] = {"price": price, "name": product_name}
                        if product_name:
                            base_name = get_base_product_name(product_name)
                            if base_name and base_name not in name_to_prices:
                                name_to_prices[base_name] = price
                logging.info(f"   +{len(prices_data) - count_before} артикулов")
            except Exception as e:
                logging.warning(f"   Ошибка: {e}")
                continue
        logging.info(f"ИТОГО: {len(prices_data)} артикулов, {len(name_to_prices)} базовых названий")
        return prices_data, name_to_prices
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        return {}, {}

def get_price_for_product(offer_id, product_name, ozon_prices_data, name_to_prices):
    if product_name:
        name_upper = product_name.strip().upper()
        if name_upper in FIXED_OZON_PRICES:
            return FIXED_OZON_PRICES[name_upper]
        for fixed_name, fixed_price in FIXED_OZON_PRICES.items():
            if fixed_name in name_upper or name_upper in fixed_name:
                return fixed_price
        if "ТУМБА ПРИКРОВАТНАЯ НАПОЛЬНАЯ С ВЫДВИЖНЫМ" in name_upper:
            return 2700
    if offer_id and offer_id in ozon_prices_data:
        return ozon_prices_data[offer_id].get("price", 0)
    if product_name:
        base_name = get_base_product_name(product_name)
        if base_name in name_to_prices:
            return name_to_prices[base_name]
    return 0

def load_catalog_from_sheet():
    gc = get_client()
    catalog = {}
    barcode_map = {}
    name_map = {}
    try:
        sh = gc.open_by_key(ID_JOURNAL)
        sheet = sh.worksheet("Каталог")
        rows = sheet.get_all_values()
        for row in rows[1:]:
            if len(row) >= 5:
                barcode = str(row[0]).strip()
                name = str(row[1]).strip()
                offer_id = str(row[4]).strip()
                if name and offer_id:
                    catalog[normalize_string(name)] = offer_id
                if barcode and offer_id:
                    barcode_map[normalize_string(barcode)] = offer_id
                if barcode and name:
                    name_map[normalize_string(barcode)] = name
        return catalog, barcode_map, name_map
    except Exception as e:
        logging.error(f"Ошибка каталога: {e}")
        return {}, {}, {}

def aggregate_data(start_dt, end_dt):
    gc = get_client()
    inventory, out_inv = {}, {}
    product_map = {}
    product_order = []
    unknown_sources = {}
    catalog, barcode_map, name_map = load_catalog_from_sheet()
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        rows_p = sh_p.worksheet("settings_products").get_all_values()[1:]
        for r in rows_p:
            if len(r) < 2 or not r[1]:
                continue
            name = str(r[1]).strip()
            if not name:
                continue
            offer_id = catalog.get(normalize_string(name), "")
            try:
                price = float(str(r[2]).replace(',', '.').strip()) if len(r) > 2 and r[2] else 0.0
            except:
                price = 0.0
            key = normalize_string(name)
            product_map[key] = {"name": name, "price": price, "offer_id": offer_id}
            product_order.append(name)
    except Exception as e:
        logging.error(f"Ошибка товаров: {e}")

    for ss_id, sheet_name in [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]:
                    continue
                row_date = parse_any_date(r[0])
                if not row_date or not (start_dt.date() <= row_date <= end_dt.date()):
                    continue
                if sheet_name == "Журнал":
                    name_raw = str(r[3]).strip() if len(r) > 3 else ""
                    qty_raw = r[4] if len(r) > 4 else 0
                    op = str(r[1]).upper() if len(r) > 1 else ""
                    sec = str(r[7]).upper() if len(r) > 7 else ""
                else:
                    name_raw = str(r[2]).strip() if len(r) > 2 else ""
                    qty_raw = r[3] if len(r) > 3 else 0
                    op = "IN"
                    sec = str(r[1]).upper() if len(r) > 1 else ""
                name_key = normalize_string(name_raw)
                meta = product_map.get(name_key)
                if not meta:
                    offer_id = catalog.get(name_key, "")
                    if not offer_id and (name_raw.upper().startswith("OZN") or name_raw.upper().startswith("KIT")):
                        offer_id = barcode_map.get(name_key, "")
                        real_name = name_map.get(name_key, name_raw)
                        name_raw = real_name
                    meta = {"name": name_raw, "price": 0.0, "offer_id": offer_id}
                name = meta.get("name", name_raw)
                offer_id = meta.get("offer_id", "")
                if not offer_id and (name.upper().startswith("OZN") or name.upper().startswith("KIT")):
                    offer_id = barcode_map.get(normalize_string(name), "")
                try:
                    qty = float(str(qty_raw).replace(',', '.'))
                except:
                    qty = 0

                if "OUT" in op:
                    out_inv[name] = out_inv.get(name, 0) + qty
                else:
                    k = normalize_string(name)
                    if k not in inventory:
                        inventory[k] = {"name": name, "p1": 0, "p2": 0, "price": meta.get("price", 0.0), "offer_id": offer_id}
                    else:
                        if offer_id and not inventory[k].get("offer_id"):
                            inventory[k]["offer_id"] = offer_id

                    # === НАДЁЖНОЕ ОПРЕДЕЛЕНИЕ УЧАСТКА ===
                    if "P1" in sec or "УЧАСТОК 1" in sec or "/1/" in sec or sec.endswith("/1") or sec == "1":
                        inventory[k]["p1"] += qty
                    elif "P2" in sec or "УЧАСТОК 2" in sec or "/2/" in sec or sec.endswith("/2") or sec == "2":
                        inventory[k]["p2"] += qty
                    else:
                        src_key = f"'{sec}'" if sec else "'(ПУСТО)'"
                        unknown_sources[src_key] = unknown_sources.get(src_key, 0) + 1
                        

        except Exception as e:
            logging.error(f"Ошибка {sheet_name}: {e}")

    # === ДИАГНОСТИКА ===
    total_p1 = sum(v['p1'] for v in inventory.values())
    total_p2 = sum(v['p2'] for v in inventory.values())
    total_out = sum(out_inv.values())
    items_with_in = sum(1 for v in inventory.values() if v['p1'] > 0 or v['p2'] > 0)
    logging.info(f"=== ПЕРИОД {start_dt.date()} - {end_dt.date()} ===")
    logging.info(f"Товаров с приходом IN: {items_with_in}")
    logging.info(f"Уникальных отгрузок OUT: {len(out_inv)}")
    logging.info(f"Всего шт на Участок 1: {total_p1}")
    logging.info(f"Всего шт на Участок 2: {total_p2}")
    logging.info(f"Всего шт отгружено: {total_out}")
    if unknown_sources:
        logging.warning(f"=== НЕРАСПОЗНАННЫЕ ИСТОЧНИКИ ({sum(unknown_sources.values())} записей, отнесены к Участку 1) ===")
        for src, count in sorted(unknown_sources.items(), key=lambda x: -x[1]):
            logging.warning(f"  {src}: {count} записей")

    return inventory, out_inv, product_order, catalog

def create_salary_pdf(inventory, period_text, salary_prices, nestandart_prices, manual_salary_prices=None, product_order=None):
    try:
        if product_order is None:
            product_order = []
        if manual_salary_prices is None:
            manual_salary_prices = {}

        buffer = io.BytesIO()
        pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4
        margin = 30

        all_items = []
        total_qty = 0
        total_salary = 0
        items_without_price = []

        for v in inventory.values():
            qty = v['p1'] + v['p2']
            if qty <= 0:
                continue
            if is_excluded(v['name']):
                continue

            name = v['name']
            name_key = normalize_string(name)
            total_qty += qty

            # Цена
            if name_key in manual_salary_prices:
                salary_price = manual_salary_prices[name_key]
            else:
                salary_price = get_salary_price_for_product(
                    name, salary_prices, nestandart_prices
                )

            # Всегда умножаем на количество
            if salary_price > 0:
                item_total = qty * salary_price
                total_salary += item_total
            else:
                item_total = 0
                items_without_price.append({
                    "name": name,
                    "qty": qty
                })

            all_items.append({
                "name": name,
                "qty": qty,
                "price": salary_price,
                "total": item_total
            })

        order_map = {name.upper(): idx for idx, name in enumerate(product_order)}
        all_items.sort(key=lambda x: order_map.get(x['name'].upper(), 9999))

        # ===== ШАПКА =====
        c.setFont(FONT_NAME, 14)
        c.drawCentredString(w / 2, h - 40, f"РАСЧЕТ ЗАРПЛАТЫ: {period_text}")

        c.setFont(FONT_NAME, 12)
        c.drawString(margin, h - 70, f"ВСЕГО ИЗДЕЛИЙ: {total_qty}")
        c.drawString(margin, h - 90, f"ИТОГО К ВЫПЛАТЕ: {total_salary:,.0f} руб.")

        y = h - 120
        c.setFont(FONT_NAME, 8)

        # ===== ТАБЛИЦА =====
        c.drawString(margin, y, "Изделие")
        c.drawRightString(margin + 350, y, "Кол-во")
        c.drawRightString(margin + 420, y, "Цена")
        c.drawRightString(margin + 500, y, "Сумма")
        y -= 15

        for item in all_items:
            if y < 50:
                c.showPage()
                y = h - 50
                c.setFont(FONT_NAME, 8)

            c.drawString(margin, y, item["name"][:50])
            c.drawRightString(margin + 350, y, f"{item['qty']}")
            c.drawRightString(margin + 420, y, f"{item['price']:.0f}" if item['price'] > 0 else "---")
            c.drawRightString(margin + 500, y, f"{item['total']:.0f}" if item['total'] > 0 else "-")
            y -= 12

        # ===== БЕЗ ЦЕНЫ =====
        if items_without_price:
            c.showPage()
            y = h - 50
            c.setFont(FONT_NAME, 10)
            c.drawString(margin, y, "ТОВАРЫ БЕЗ ЦЕНЫ:")
            y -= 20
            c.setFont(FONT_NAME, 8)

            for item in items_without_price:
                if y < 50:
                    c.showPage()
                    y = h - 50
                    c.setFont(FONT_NAME, 8)

                c.drawString(margin, y, f"- {item['name']} : {item['qty']} шт")
                y -= 12

        c.save()
        buffer.seek(0)

        return buffer, total_qty, total_salary, items_without_price

    except Exception as e:
        logging.error(f"Ошибка PDF зарплаты: {e}")
        traceback.print_exc()
        raise
def create_styled_pdf(inventory, out_inv, period_text, mode="finance", product_order=None, ozon_prices=None):
    try:
        if product_order is None:
            product_order = []
        if ozon_prices is None:
            ozon_prices = {}
        buffer = io.BytesIO()
        pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4
        margin, col_gap = 32, 16
        col_w = (w - margin * 2 - col_gap) / 2
        p1_data = [(v['name'], v['p1'], v.get('price', 0), v.get('offer_id', '')) for v in inventory.values() if v['p1'] > 0]
        p2_data = [(v['name'], v['p2'], v.get('price', 0), v.get('offer_id', '')) for v in inventory.values() if v['p2'] > 0]
        if mode == "finance":
            p1_data = [item for item in p1_data if not is_excluded(item[0])]
            p2_data = [item for item in p2_data if not is_excluded(item[0])]
        order_map = {name.upper(): idx for idx, name in enumerate(product_order)}
        p1 = sorted(p1_data, key=lambda x: order_map.get(x[0].upper(), 9999))
        p2 = sorted(p2_data, key=lambda x: order_map.get(x[0].upper(), 9999))
        outs = sorted(out_inv.items())
        sum_p1 = sum(qty for _, qty, _, _ in p1)
        sum_p2 = sum(qty for _, qty, _, _ in p2)
        sum_outs = sum(qty for _, qty in outs)
        hyp_revenue = 0
        items_with_prices = 0
        items_without_prices = 0
        for name, q, local_price, offer_id in p1 + p2:
            price = ozon_prices.get(offer_id, 0) if offer_id else 0
            if not price:
                price = ozon_prices.get(name, 0)
            if price > 0:
                hyp_revenue += q * price
                items_with_prices += 1
            else:
                items_without_prices += 1
        total_val = sum((v['p1'] + v['p2']) * v.get('price', 0) for v in inventory.values()) if mode == "finance" else (sum_p1 + sum_p2)

        all_left = []
        all_right = []

        if mode == "finance":
            if p1:
                all_left += [("HEADER", "УЧАСТОК 1", "#E8F0FE")]
                for n, q, p, _ in p1:
                    all_left.append((f"{n} ({p:.0f}р)", q * p))
                all_left += [("TOTAL_BLOCK", "ИТОГО УЧ. 1:", sum(q * p for _, q, p, _ in p1))]
            if p2:
                all_left += [("HEADER", "УЧАСТОК 2", "#E8F0FE")]
                for n, q, p, _ in p2:
                    all_left.append((f"{n} ({p:.0f}р)", q * p))
                all_left += [("TOTAL_BLOCK", "ИТОГО УЧ. 2:", sum(q * p for _, q, p, _ in p2))]
        elif mode == "hypothetical":
            items_all = p1 + p2
            if items_all:
                all_left += [("HEADER", "ПРИХОД НА СКЛАД", "#E8F0FE")]
                for name, q, local_price, offer_id in items_all:
                    price = ozon_prices.get(offer_id, 0) if offer_id else 0
                    if not price:
                        price = ozon_prices.get(name, 0)
                    row_revenue = q * price
                    if price > 0:
                        label = f"{name} ({price:.0f}р x {q:.0f})"
                    else:
                        label = f"{name} (нет цены)"
                    all_left.append((label, row_revenue))
                all_left += [("TOTAL_BLOCK", "ИТОГО ШТ:", sum_p1 + sum_p2)]
            all_right += [("HEADER", "ВЫРУЧКА OZON", "#E6F4EA")]
            for name, q, local_price, offer_id in items_all:
                price = ozon_prices.get(offer_id, 0) if offer_id else 0
                if not price:
                    price = ozon_prices.get(name, 0)
                if price > 0:
                    all_right.append((name, q * price))
            all_right += [("TOTAL_BLOCK", f"С ценой: {items_with_prices} шт", 0)]
            all_right += [("TOTAL_BLOCK", f"Без цены: {items_without_prices} шт", 0)]
            all_right += [("TOTAL_BLOCK", "ИТОГО ВЫРУЧКА:", hyp_revenue)]
        else:
            if p1:
                all_left += [("HEADER", "УЧАСТОК 1", "#E8F0FE")]
                for n, q, _, _ in p1:
                    all_left.append((n, q))
                all_left += [("TOTAL_BLOCK", "ИТОГО УЧ. 1:", sum_p1)]
            if p2:
                all_left += [("HEADER", "УЧАСТОК 2", "#E8F0FE")]
                for n, q, _, _ in p2:
                    all_left.append((n, q))
                all_left += [("TOTAL_BLOCK", "ИТОГО УЧ. 2:", sum_p2)]
            if outs:
                all_right += [("HEADER", "ОТГРУЗКА (OUT)", "#FFF2CC")]
                for name, qty in outs:
                    all_right.append((name, qty))
                all_right += [("TOTAL_BLOCK", "ИТОГО ОТГРУЗКА:", sum_outs)]

        def draw_frame(page):
            c.setFont(FONT_NAME, 13)
            title = "ВЫРУЧКА OZON (мин. цена)" if mode == "hypothetical" else ("ФИНАНСОВЫЙ ОТЧЕТ" if mode == "finance" else "ОТЧЕТ СКЛАДА")
            c.drawCentredString(w / 2, h - 40, f"{title}: {period_text} (Стр. {page})")
            c.setFillColor(colors.HexColor("#F3F3F3"))
            c.rect(margin, 55, w - margin * 2, 22, fill=1, stroke=1)
            c.setFillColor(colors.black)
            c.setFont(FONT_NAME, 9.5)
            if mode == "finance":
                foot_txt = f"ОБЩАЯ СУММА: {total_val:.0f} руб."
            elif mode == "hypothetical":
                foot_txt = f"ВЫРУЧКА OZON: {hyp_revenue:.0f} руб."
            else:
                foot_txt = f"ПРИХОД: {total_val:.0f} | ОТГРУЗКА: {sum_outs:.0f}"
            c.drawCentredString(w / 2, 63, foot_txt)

        def item_height(it):
            if it[0] in ("HEADER",):
                return 26
            elif it[0] == "TOTAL_BLOCK":
                return 32
            else:
                name = it[0]
                lines = simpleSplit(str(name), FONT_NAME, 7.5, col_w - 55)
                return 27 if len(lines) > 1 else 13

        def draw_items_in_col(items, x, y_start):
            y = y_start
            i = 0
            for i, it in enumerate(items):
                needed = item_height(it)
                if y - needed < 115:
                    return items[i:], y
                if it[0] == "HEADER":
                    c.setFillColor(colors.HexColor(it[2]))
                    c.rect(x, y - 17, col_w, 17, fill=1, stroke=1)
                    c.setFillColor(colors.black)
                    c.setFont(FONT_NAME, 9.5)
                    c.drawCentredString(x + col_w / 2, y - 11, it[1])
                    y -= 26
                elif it[0] == "TOTAL_BLOCK":
                    c.setStrokeColor(colors.black)
                    c.line(x, y - 3, x + col_w, y - 3)
                    c.setFont(FONT_NAME, 9)
                    c.drawString(x + 4, y - 14, it[1])
                    if it[2] != 0:
                        c.drawRightString(x + col_w - 4, y - 14, f"{float(it[2]):.0f}")
                    y -= 32
                else:
                    name, val = it
                    c.setStrokeColor(colors.HexColor("#E0E0E0"))
                    c.line(x, y - 13, x + col_w, y - 13)
                    c.setFont(FONT_NAME, 7.5)
                    lines = simpleSplit(str(name), FONT_NAME, 7.5, col_w - 55)
                    if len(lines) > 1:
                        c.drawString(x + 4, y - 8, lines[0])
                        c.drawString(x + 4, y - 19, lines[1])
                        c.drawRightString(x + col_w - 4, y - 8, f"{float(val):.0f}")
                        y -= 27
                    else:
                        c.drawString(x + 4, y - 8, str(name))
                        c.drawRightString(x + col_w - 4, y - 8, f"{float(val):.0f}")
                        y -= 13
            return [], y

        page_num = 1
        left_remaining = list(all_left)
        right_remaining = list(all_right)

        while left_remaining or right_remaining:
            draw_frame(page_num)
            y_start = h - 78

            left_remaining, _ = draw_items_in_col(left_remaining, margin, y_start)
            right_remaining, _ = draw_items_in_col(right_remaining, margin + col_w + col_gap, y_start)

            if left_remaining or right_remaining:
                c.showPage()
                page_num += 1
            else:
                break

        c.save()
        buffer.seek(0)
        return buffer
    except Exception as e:
        logging.error(f"Ошибка PDF: {e}")
        traceback.print_exc()
        raise

def create_summary_pdf(inventory, period_text, product_order=None, manual_prices=None):
    try:
        if product_order is None:
            product_order = []
        if manual_prices is None:
            manual_prices = {}

        salary_prices = load_salary_prices()
        nestandart_prices = load_nestandart_prices()

        buffer = io.BytesIO()
        pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
        c = canvas.Canvas(buffer, pagesize=A4)
        w, h = A4
        margin = 30

        total_qty = 0
        total_sum = 0
        all_items = []

        for v in inventory.values():
            qty = v['p1'] + v['p2']
            if qty <= 0:
                continue

            name = v['name']
            name_key = normalize_string(name)

            if name_key in manual_prices:
                price = manual_prices[name_key]
            else:
                price = get_salary_price_for_product(
                    name, salary_prices, nestandart_prices
                )

            total_qty += qty
            total_sum += qty * price

            all_items.append({
                "name": name,
                "qty": qty,
                "price": price,
                "total": qty * price
            })

        order_map = {name.upper(): idx for idx, name in enumerate(product_order)}
        all_items.sort(key=lambda x: order_map.get(x['name'].upper(), 9999))

        c.setFont(FONT_NAME, 14)
        c.drawCentredString(w / 2, h - 40, f"СВОДНЫЙ ОТЧЕТ: {period_text}")

        c.setFont(FONT_NAME, 11)
        c.drawString(margin, h - 70, f"Всего изделий: {total_qty}")
        c.drawString(margin, h - 90, f"Общая сумма: {total_sum:,.0f} руб.")

        y = h - 120
        c.setFont(FONT_NAME, 8)

        for item in all_items:
            if y < 50:
                c.showPage()
                y = h - 50
                c.setFont(FONT_NAME, 8)

            c.drawString(margin, y, item["name"][:50])
            c.drawRightString(margin + 350, y, f"{item['qty']}")
            c.drawRightString(margin + 420, y, f"{item['price']:.0f}")
            c.drawRightString(margin + 500, y, f"{item['total']:.0f}")
            y -= 12

        c.save()
        buffer.seek(0)
        return buffer, total_qty, total_sum

    except Exception as e:
        logging.error(f"Ошибка сводного PDF: {e}")
        raise

async def send_pdf(message, pdf_buffer, filename):
    try:
        data = pdf_buffer.getvalue()
        logging.info(f"Отправляю PDF: {filename}, размер: {len(data)} байт")
        await message.answer_document(BufferedInputFile(data, filename=filename))
        logging.info(f"PDF отправлен: {filename}")
    except Exception as e:
        logging.error(f"Ошибка отправки PDF: {e}")
        traceback.print_exc()
        await message.answer(f"Ошибка отправки: {str(e)}")

def get_months_kb(p):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=months[j+k], callback_data=f"{p}_{j+k+1:02d}") for k in range(3) if j+k < 12]
        for j in range(0, 12, 3)
    ])

def get_days_kb(m, p):
    year = REPORT_YEAR  # ← год для отчётов
    last = calendar.monthrange(year, int(m))[1]
    rows = []
    for w in range(1, last + 1, 7):
        row = []
        for d in range(w, min(w + 7, last + 1)):
            callback = f"{p}_{d:02d}.{m}.{year}"
            row.append(InlineKeyboardButton(text=str(d), callback_data=callback))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer(f"Твой ID: {m.from_user.id}")
    kb = [
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]
    ]
    if m.from_user.id in ADMIN_IDS:
        kb.append([KeyboardButton(text="📋 СВОДНЫЙ ОТЧЁТ")])
        kb.append([KeyboardButton(text="💵 Посчитать зарплату")])
    await m.answer(f"Бот готов!\n⚙️ Год отчётов: {REPORT_YEAR}\n📅 Дата сервера: {datetime.now().strftime('%d.%m.%Y %H:%M')}", reply_markup=ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True))

def find_salary_items_without_price(inventory, salary_prices, nestandart_prices):
    items_no_price = []
    for v in inventory.values():
        qty = v['p1'] + v['p2']
        if qty <= 0:
            continue
        if is_excluded(v['name']):
            continue
        name = v['name']
        price = get_salary_price_for_product(name, salary_prices, nestandart_prices)
        if price == 0:
            items_no_price.append({"name": name, "qty": qty, "key": normalize_string(name)})
    return items_no_price

async def ask_next_salary_price(message, state: FSMContext):
    data = await state.get_data()
    pending_items = data.get("salary_pending_items", [])
    current_index = data.get("salary_current_index", 0)
    if current_index >= len(pending_items):
        await finalize_salary_report(message, state)
        return
    item = pending_items[current_index]
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить (цена = 0)", callback_data="sal_skip_price")],
        [InlineKeyboardButton(text="Пропустить все оставшиеся", callback_data="sal_skip_all")]
    ])
    await message.answer(
        f"⚠️ Нет цены для расчёта зарплаты:\n\n"
        f"📦 {item['name']}\n"
        f"📊 Кол-во: {item['qty']:.0f} шт\n\n"
        f"({current_index + 1} из {len(pending_items)})\n\n"
        f"💰 Введите стоимость за ОДНУ ЕДИНИЦУ (будет записано в SalaryManual):",
        reply_markup=ikb
    )
    await state.set_state(SalaryStates.waiting_salary_price)
@dp.callback_query(F.data == "sal_today")
async def sal_today_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()

    n = datetime.now()
    inv, out, prod_order, _ = aggregate_data(n, n)
    period_text = n.strftime('%d.%m.%Y')

    await start_salary_generation(cb.message, inv, prod_order, period_text, state)


@dp.callback_query(F.data == "sal_week")
async def sal_week_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()

    end = datetime.now()
    start_d = end - timedelta(days=6)

    inv, out, prod_order, _ = aggregate_data(start_d, end)
    period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"

    await start_salary_generation(cb.message, inv, prod_order, period_text, state)


@dp.callback_query(F.data == "sal_month")
async def sal_month_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer()

    end = datetime.now()
    start_d = end.replace(day=1)

    inv, out, prod_order, _ = aggregate_data(start_d, end)
    period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"

    await start_salary_generation(cb.message, inv, prod_order, period_text, state)
async def finalize_salary_report(message, state: FSMContext):

    data = await state.get_data()

    inv = data.get("salary_inventory", {})
    period = data.get("salary_period", "")
    manual_prices = load_salary_manual_prices()   # ✅ ТОЛЬКО manual

    # ✅ считаем только из SalaryManual
    all_items, total_qty, total_sum, _ = calculate_inventory(
        inv, manual_prices
    )

    pdf_buffer = create_beautiful_pdf(
        all_items,
        total_qty,
        total_sum,
        period
    )

    msg = f"ЗАРПЛАТА за {period}\n\n"
    msg += f"Изделий: {int(total_qty)}\n"
    msg += f"К выплате: {total_sum:,.0f} руб."

    await message.answer(msg)
    await send_pdf(message, pdf_buffer, "Salary_Report.pdf")

    await state.clear()
@dp.message(F.text == "💵 Посчитать зарплату")
async def salary_start(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.update_data(rep_mode="salary")
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СЕГОДНЯ", callback_data="sal_today")],
        [InlineKeyboardButton(text="НЕДЕЛЯ", callback_data="sal_week")],
        [InlineKeyboardButton(text="МЕСЯЦ", callback_data="sal_month")],
        [InlineKeyboardButton(text="Выбрать день", callback_data="set_single")],
        [InlineKeyboardButton(text="Выбрать период", callback_data="set_range")]
    ])
    await m.answer(
        "💵 РАСЧЕТ ЗАРПЛАТЫ\n\n"
        "Цены берутся из:\n"
        "- Основная таблица зарплаты\n"
        "- Таблица Nestandart\n\n"
        "Если цена = 0 → бот спросит цену и запишет в Nestandart\n"
        "Nestandart считается за 1 шт (не qty * цена)\n\n"
        "Выберите период:",
        reply_markup=ikb
    )

async def start_salary_generation(message, inv, prod_order, period, state: FSMContext):

    salary_manual = load_salary_manual_prices()   # ✅ только manual

    all_items, total_qty, total_sum, items_without_price = calculate_inventory(
        inv, salary_manual
    )

    if items_without_price:
        await state.update_data(
            salary_inventory=inv,
            salary_pending_items=items_without_price,
            salary_current_index=0,
            salary_manual_prices=salary_manual
        )

        await ask_next_salary_price(message, state)
        return

    pdf_buffer = create_beautiful_pdf(all_items, total_qty, total_sum, period)

    msg = f"ЗАРПЛАТА за {period}\n\n"
    msg += f"Изделий: {int(total_qty)}\n"
    msg += f"К выплате: {total_sum:,.0f} руб."

    await message.answer(msg)
    await send_pdf(message, pdf_buffer, "Salary_Report.pdf")

    await state.clear()

async def sal_enter_prices_cb(cb: types.CallbackQuery, state: FSMContext):
    try:
        await cb.message.delete()
    except:
        pass
    await ask_next_salary_price(cb.message, state)
    await cb.answer()

@dp.message(SalaryStates.waiting_salary_price)
async def handle_salary_price_input(m: types.Message, state: FSMContext):
    data = await state.get_data()
    pending_items = data.get("salary_pending_items", [])
    current_index = data.get("salary_current_index", 0)
    manual_prices = data.get("salary_manual_prices", {})
    if current_index >= len(pending_items):
        await state.clear()
        return
    item = pending_items[current_index]
    price = parse_price(m.text)
    if price > 0:
        manual_prices[normalize_string(item["name"])] = price
        saved = save_to_salary_manual(item["name"], price)
        if saved:
            await m.answer(
                f"✅ Цена {price:.0f} руб. сохранена\n"
                f"📝 SalaryManual: {item['name']}\n"
                f"(считается за 1 шт)"
            )
        else:
            await m.answer(
                f"✅ Цена {price:.0f} руб. принята\n"
                f"⚠️ Не удалось записать в Nestandart (будет использована только в этом отчёте)"
            )
    else:
        await m.answer(f"⏭ Цена = 0 (пропущено)")
    await state.update_data(
        salary_current_index=current_index + 1,
        salary_manual_prices=manual_prices
    )
    await ask_next_salary_price(m, state)

@dp.callback_query(F.data == "sal_skip_price")
async def sal_skip_price_cb(cb: types.CallbackQuery, state: FSMContext):
    await cb.answer("Пропущено")
    data = await state.get_data()
    current_index = data.get("salary_current_index", 0)
    await state.update_data(salary_current_index=current_index + 1)
    try:
        await cb.message.delete()
    except:
        pass
    await ask_next_salary_price(cb.message, state)
   

@dp.callback_query(F.data == "sal_skip_all")
async def sal_skip_all_cb(cb: types.CallbackQuery, state: FSMContext):
    try:
        await cb.message.delete()
    except:
        pass
    await cb.message.answer("⏭ Все без цены пропущены...")
    await finalize_salary_report(cb.message, state)
    await cb.answer()

@dp.callback_query(F.data == "sal_today")
async def sal_today_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    await cb.message.edit_text("⏳ Загружаю данные и цены...")
    n = datetime.now()
    try:
        inv, out, prod_order, _ = aggregate_data(n, n)
        period_text = n.strftime('%d.%m.%Y')
        try:
            await cb.message.delete()
        except:
            pass
        await start_salary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    

@dp.callback_query(F.data == "sal_week")
async def sal_week_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    await cb.message.edit_text("⏳ Загружаю данные и цены...")
    end = datetime.now()
    start_d = end - timedelta(days=6)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        try:
            await cb.message.delete()
        except:
            pass
        await start_salary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    

@dp.callback_query(F.data == "sal_month")
async def sal_month_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    await cb.message.edit_text("⏳ Загружаю данные и цены...")
    end = datetime.now()
    start_d = end.replace(day=1)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        try:
            await cb.message.delete()
        except:
            pass
        await start_salary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    

@dp.message(F.text == "📋 СВОДНЫЙ ОТЧЁТ")
async def summary_start(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS:
        return
    await state.clear()
    await state.update_data(rep_mode="summary")
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СЕГОДНЯ", callback_data="sum_today")],
        [InlineKeyboardButton(text="НЕДЕЛЯ", callback_data="sum_week")],
        [InlineKeyboardButton(text="МЕСЯЦ", callback_data="sum_month")],
        [InlineKeyboardButton(text="Выбрать день", callback_data="set_single")],
        [InlineKeyboardButton(text="Выбрать период", callback_data="set_range")]
    ])
    await m.answer("СВОДНЫЙ ОТЧЁТ\n\nСравнение:\n- Себестоимость (цех)\n- OZON (мин. цена)\n\nЕсли цена OZON = 0, бот спросит цену\n\nВыберите период:", reply_markup=ikb)

def find_items_without_ozon_price(inventory, ozon_prices_data, name_to_prices):
    items_no_price = []
    for v in inventory.values():
        qty = v['p1'] + v['p2']
        if qty <= 0:
            continue
        if is_excluded(v['name']):
            continue
        name = v['name']
        offer_id = v.get('offer_id', '')
        ozon_price = get_price_for_product(offer_id, name, ozon_prices_data, name_to_prices)
        if ozon_price == 0:
            items_no_price.append({"name": name, "qty": qty, "key": normalize_string(name)})
    return items_no_price

async def process_summary_with_prices(message, inv, prod_order, period_text, manual_prices, state):

    # 1. Загружаем обычные цены (основные таблицы)
    salary_prices = load_salary_prices()
    nestandart_prices = load_nestandart_prices()

    # 2. Собираем словарь цен
    price_dict = {}

    for name, data in salary_prices.items():
        price_dict[name] = data["price"]

    for name, data in nestandart_prices.items():
        price_dict[name] = data["price"]

    # 3. Считаем
    all_items, total_qty, total_sum, _ = calculate_inventory(inv, price_dict)

    # 4. Делаем PDF
    pdf_buffer = create_beautiful_pdf(all_items, total_qty, total_sum, period_text)

    # 5. Сообщение
    msg = f"СВОДКА за {period_text}\n\n"
    msg += f"Изделий: {int(total_qty)}\n"
    msg += f"Сумма: {total_sum:,.0f} руб."

    await message.answer(msg)
    await send_pdf(
        message,
        pdf_buffer,
        f"Summary_{period_text.replace(' ', '_').replace('-', '_')}.pdf"
    )

    await state.clear()

async def ask_next_price(message, state: FSMContext):
    data = await state.get_data()
    pending_items = data.get("pending_items", [])
    current_index = data.get("current_item_index", 0)
    if current_index >= len(pending_items):
        inv = data.get("report_inventory", {})
        prod_order = data.get("report_prod_order", [])
        period_text = data.get("report_period", "")
        manual_prices = data.get("collected_prices", {})
        await process_summary_with_prices(message, inv, prod_order, period_text, manual_prices, state)
        return
    item = pending_items[current_index]
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Пропустить (цена = 0)", callback_data="skip_price")],
        [InlineKeyboardButton(text="Пропустить все", callback_data="skip_all_prices")]
    ])
    await message.answer(
        f"Укажите цену OZON для:\n\n"
        f"{item['name']}\n"
        f"Количество: {item['qty']:.0f} шт\n\n"
        f"({current_index + 1} из {len(pending_items)})\n\n"
        f"Введите цену числом:",
        reply_markup=ikb
    )
    await state.set_state(ReportStates.waiting_ozon_price)

@dp.message(ReportStates.waiting_ozon_price)
async def handle_price_input(m: types.Message, state: FSMContext):
    data = await state.get_data()
    pending_items = data.get("pending_items", [])
    current_index = data.get("current_item_index", 0)
    collected_prices = data.get("collected_prices", {})
    if current_index >= len(pending_items):
        await state.clear()
        return
    item = pending_items[current_index]
    price = parse_price(m.text)
    if price > 0:
        collected_prices[item["key"]] = price
        await m.answer(f"Цена {price:.0f} р сохранена")
    else:
        await m.answer(f"Цена 0 р")
    await state.update_data(
        current_item_index=current_index + 1,
        collected_prices=collected_prices
    )
    await ask_next_price(m, state)

@dp.callback_query(F.data == "skip_price")
async def skip_price_cb(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_index = data.get("current_item_index", 0)
    await state.update_data(current_item_index=current_index + 1)
    try:
        await cb.message.delete()
    except:
        pass
    await ask_next_price(cb.message, state)
    await cb.answer("Пропущено")

@dp.callback_query(F.data == "skip_all_prices")
async def skip_all_prices_cb(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    inv = data.get("report_inventory", {})
    prod_order = data.get("report_prod_order", [])
    period_text = data.get("report_period", "")
    manual_prices = data.get("collected_prices", {})
    try:
        await cb.message.delete()
    except:
        pass
    await cb.message.answer("Генерирую отчет...")
    await process_summary_with_prices(cb.message, inv, prod_order, period_text, manual_prices, state)
    await cb.answer()

async def start_summary_generation(message, inv, prod_order, period_text, state: FSMContext):
    ozon_prices_data, name_to_prices = load_ozon_prices_from_sheet()
    items_no_price = find_items_without_ozon_price(inv, ozon_prices_data, name_to_prices)
    if not items_no_price:
        await process_summary_with_prices(message, inv, prod_order, period_text, {}, state)
        return
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ввести цены вручную", callback_data="enter_prices")],
        [InlineKeyboardButton(text="Пропустить (оставить 0)", callback_data="skip_all_prices")]
    ])
    names_preview = "\n".join([f"- {item['name'][:40]}..." if len(item['name']) > 40 else f"- {item['name']}" for item in items_no_price[:5]])
    if len(items_no_price) > 5:
        names_preview += f"\n... и ещё {len(items_no_price) - 5}"
    await state.update_data(
        pending_items=items_no_price,
        current_item_index=0,
        collected_prices={},
        report_inventory=inv,
        report_prod_order=prod_order,
        report_period=period_text
    )
    await message.answer(
        f"Найдено {len(items_no_price)} товаров без цены OZON:\n\n{names_preview}\n\n"
        f"Хотите ввести цены вручную?",
        reply_markup=ikb
    )

@dp.callback_query(F.data == "enter_prices")
async def enter_prices_cb(cb: types.CallbackQuery, state: FSMContext):
    try:
        await cb.message.delete()
    except:
        pass
    await ask_next_price(cb.message, state)
    await cb.answer()

@dp.callback_query(F.data == "sum_today")
async def sum_today_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Собираю данные...")
    n = datetime.now()
    try:
        inv, out, prod_order, _ = aggregate_data(n, n)
        period_text = n.strftime('%d.%m.%Y')
        try:
            await cb.message.delete()
        except:
            pass
        await start_summary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "sum_week")
async def sum_week_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Собираю данные...")
    end = datetime.now()
    start_d = end - timedelta(days=6)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        try:
            await cb.message.delete()
        except:
            pass
        await start_summary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "sum_month")
async def sum_month_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Собираю данные...")
    end = datetime.now()
    start_d = end.replace(day=1)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        try:
            await cb.message.delete()
        except:
            pass
        await start_summary_generation(cb.message, inv, prod_order, period_text, state)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        traceback.print_exc()
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    await cb.answer()

@dp.message(F.text == "📊 Выручка OZON")
async def hypothetical_start(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_IDS:
        return
    await state.clear()
    await state.update_data(rep_mode="hypothetical")
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СЕГОДНЯ", callback_data="hyp_today")],
        [InlineKeyboardButton(text="НЕДЕЛЯ", callback_data="hyp_week")],
        [InlineKeyboardButton(text="МЕСЯЦ", callback_data="hyp_month")],
        [InlineKeyboardButton(text="Выбрать день", callback_data="set_single")],
        [InlineKeyboardButton(text="Выбрать период", callback_data="set_range")]
    ])
    await m.answer("Выручка OZON\n\nМинимальная цена для выплат\n\nВыберите период:", reply_markup=ikb)

async def build_hypothetical_report(inv, out, prod_order, period_text):
    ozon_prices_data, name_to_prices = load_ozon_prices_from_sheet()
    ozon_prices = {}
    for key, item in inv.items():
        offer_id = item.get("offer_id", "")
        name = item.get("name", "")
        price = get_price_for_product(offer_id, name, ozon_prices_data, name_to_prices)
        if offer_id and price > 0:
            ozon_prices[offer_id] = price
        elif price > 0:
            ozon_prices[name] = price
    matched = sum(1 for item in inv.values() if item.get("offer_id") in ozon_prices or item.get("name") in ozon_prices)
    pdf_buffer = create_styled_pdf(inv, out, period_text, mode="hypothetical", product_order=prod_order, ozon_prices=ozon_prices)
    return pdf_buffer, len(ozon_prices), matched

@dp.callback_query(F.data == "hyp_today")
async def hyp_today_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Загружаю цены...")
    n = datetime.now()
    try:
        inv, out, prod_order, _ = aggregate_data(n, n)
        period_text = n.strftime('%d.%m.%Y')
        pdf_buffer, prices_count, matched = await build_hypothetical_report(inv, out, prod_order, period_text)
        await cb.message.answer(f"Цен: {prices_count}\nСопоставлено: {matched} товаров")
        await send_pdf(cb.message, pdf_buffer, f"Ozon_{period_text}.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "hyp_week")
async def hyp_week_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Загружаю цены...")
    end = datetime.now()
    start_d = end - timedelta(days=6)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        pdf_buffer, prices_count, matched = await build_hypothetical_report(inv, out, prod_order, period_text)
        await cb.message.answer(f"Цен: {prices_count}\nСопоставлено: {matched} товаров")
        await send_pdf(cb.message, pdf_buffer, "Ozon_Week.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "hyp_month")
async def hyp_month_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.message.edit_text("Загружаю цены...")
    end = datetime.now()
    start_d = end.replace(day=1)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        pdf_buffer, prices_count, matched = await build_hypothetical_report(inv, out, prod_order, period_text)
        await cb.message.answer(f"Цен: {prices_count}\nСопоставлено: {matched} товаров")
        await send_pdf(cb.message, pdf_buffer, "Ozon_Month.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.message(F.text == "💰 Финансы")
async def fin_mode_select(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_IDS:
        return
    await state.clear()
    await state.update_data(rep_mode="finance")
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="СЕГОДНЯ", callback_data="fin_today")],
        [InlineKeyboardButton(text="НЕДЕЛЯ", callback_data="fin_week")],
        [InlineKeyboardButton(text="МЕСЯЦ", callback_data="fin_month")],
        [InlineKeyboardButton(text="Выбрать день", callback_data="set_single")],
        [InlineKeyboardButton(text="Выбрать период", callback_data="set_range")]
    ])
    await m.answer("Финансовый отчет\nВыберите период:", reply_markup=ikb)

@dp.callback_query(F.data == "fin_today")
async def fin_today_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_chat_action(cb.message.chat.id, action="upload_document")
    n = datetime.now()
    try:
        inv, out, prod_order, _ = aggregate_data(n, n)
        pdf_buffer = create_styled_pdf(inv, out, n.strftime("%d.%m.%Y"), mode="finance", product_order=prod_order)
        await send_pdf(cb.message, pdf_buffer, f"Finance_{n.strftime('%d.%m.%Y')}.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "fin_week")
async def fin_week_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_chat_action(cb.message.chat.id, action="upload_document")
    end = datetime.now()
    start_d = end - timedelta(days=6)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        pdf_buffer = create_styled_pdf(inv, out, period_text, mode="finance", product_order=prod_order)
        await send_pdf(cb.message, pdf_buffer, "Finance_Week.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.callback_query(F.data == "fin_month")
async def fin_month_cb(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await bot.send_chat_action(cb.message.chat.id, action="upload_document")
    end = datetime.now()
    start_d = end.replace(day=1)
    try:
        inv, out, prod_order, _ = aggregate_data(start_d, end)
        period_text = f"{start_d.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}"
        pdf_buffer = create_styled_pdf(inv, out, period_text, mode="finance", product_order=prod_order)
        await send_pdf(cb.message, pdf_buffer, "Finance_Month.pdf")
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
    try:
        await cb.message.delete()
    except:
        pass
    await state.clear()
    await cb.answer()

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message, state: FSMContext, bot: Bot):
    await state.clear()
    await bot.send_chat_action(m.chat.id, action="upload_document")
    n = datetime.now()
    try:
        inv, out, prod_order, _ = aggregate_data(n, n)
        pdf_buffer = create_styled_pdf(inv, out, n.strftime("%d.%m.%Y"), mode="stock", product_order=prod_order)
        await send_pdf(m, pdf_buffer, "Today_Stock.pdf")
    except Exception as e:
        await m.answer(f"Ошибка: {str(e)}")

@dp.message(F.text == "📊 Отчет за день")
async def report_day_start(m: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(rep_mode="stock")
    await m.answer(f"Выберите месяц ({REPORT_YEAR} год):", reply_markup=get_months_kb("mon_single"))

@dp.message(F.text == "📅 Выбрать промежуток")
async def report_range_start(m: types.Message, state: FSMContext):
    await state.clear()
    await state.update_data(rep_mode="stock")
    await m.answer(f"Месяц НАЧАЛА ({REPORT_YEAR} год):", reply_markup=get_months_kb("mon_start"))

@dp.callback_query(F.data == "set_single")
async def set_single_cb(cb: types.CallbackQuery):
    await cb.message.edit_text(f"Выберите месяц ({REPORT_YEAR} год):", reply_markup=get_months_kb("mon_single"))
    await cb.answer()

@dp.callback_query(F.data == "set_range")
async def set_range_cb(cb: types.CallbackQuery):
    await cb.message.edit_text(f"Месяц НАЧАЛА ({REPORT_YEAR} год):", reply_markup=get_months_kb("mon_start"))
    await cb.answer()

@dp.callback_query(F.data.startswith("mon_single_"))
async def mon_single(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(m, "day_single"))
    await cb.answer()

@dp.callback_query(F.data.startswith("day_single_"))
async def day_single_finish(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    sdata = await state.get_data()
    mode = sdata.get("rep_mode", "stock")
    d_str = cb.data.split("_")[2]
    dt = datetime.strptime(d_str, "%d.%m.%Y")
    logging.info(f"📅 Выбрана дата: {d_str}, режим: {mode}")
    await cb.message.edit_text("Загружаю данные...")
    try:
        inv, out, prod_order, _ = aggregate_data(dt, dt)
        if mode == "hypothetical":
            pdf_buffer, prices_count, matched = await build_hypothetical_report(inv, out, prod_order, d_str)
            await cb.message.answer(f"Цен: {prices_count}, сопоставлено: {matched}")
            await send_pdf(cb.message, pdf_buffer, f"Ozon_{d_str}.pdf")
            try:
                await cb.message.delete()
            except:
                pass
            await state.clear()
        elif mode == "summary":
            try:
                await cb.message.delete()
            except:
                pass
            await start_summary_generation(cb.message, inv, prod_order, d_str, state)
        elif mode == "salary":
            try:
                await cb.message.delete()
            except:
                pass
            await start_salary_generation(cb.message, inv, prod_order, d_str, state)
        else:
            pdf_buffer = create_styled_pdf(inv, out, d_str, mode=mode, product_order=prod_order)
            fname = f"Finance_{d_str}.pdf" if mode == "finance" else f"Report_{d_str}.pdf"
            await send_pdf(cb.message, pdf_buffer, fname)
            try:
                await cb.message.delete()
            except:
                pass
            await state.clear()
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    await cb.answer()

@dp.callback_query(F.data.startswith("mon_start_"))
async def mon_start_cb(cb: types.CallbackQuery, state: FSMContext):
    m = cb.data.split("_")[2]
    await state.update_data(start_date=m)
    await cb.message.edit_text("Число НАЧАЛА:", reply_markup=get_days_kb(m, "day_start"))
    await cb.answer()

@dp.callback_query(F.data.startswith("day_start_"))
async def day_start_save(cb: types.CallbackQuery, state: FSMContext):
    d_start = cb.data.split("_")[2]
    logging.info(f"📅 Выбрана дата НАЧАЛА: {d_start}")
    await state.update_data(start_date=d_start)
    await cb.message.edit_text(f"Начало: {d_start}. Месяц КОНЦА:", reply_markup=get_months_kb("mon_end"))
    await cb.answer()

@dp.callback_query(F.data.startswith("mon_end_"))
async def mon_end_cb(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Число КОНЦА:", reply_markup=get_days_kb(m, "day_end"))
    await cb.answer()

@dp.callback_query(F.data.startswith("day_end_"))
async def day_end_finish(cb: types.CallbackQuery, state: FSMContext, bot: Bot):
    await cb.answer()
    sdata = await state.get_data()
    mode = sdata.get("rep_mode", "stock")
    d1_str = sdata.get("start_date")
    d2_str = cb.data.split("_")[2]
    if not d1_str:
        await cb.message.answer("Дата начала не найдена.")
        await state.clear()
        return
    dt1 = datetime.strptime(d1_str, "%d.%m.%Y")
    dt2 = datetime.strptime(d2_str, "%d.%m.%Y")
    period = f"{d1_str} - {d2_str}"
    logging.info(f"📅 Период: {period}, режим: {mode}")
    await cb.message.edit_text("Загружаю данные...")
    try:
        inv, out, prod_order, _ = aggregate_data(dt1, dt2)
        if mode == "hypothetical":
            pdf_buffer, prices_count, matched = await build_hypothetical_report(inv, out, prod_order, period)
            await cb.message.answer(f"Цен: {prices_count}, сопоставлено: {matched}")
            await send_pdf(cb.message, pdf_buffer, "Ozon_Range.pdf")
            try:
                await cb.message.delete()
            except:
                pass
            await state.clear()
        elif mode == "summary":
            try:
                await cb.message.delete()
            except:
                pass
            await start_summary_generation(cb.message, inv, prod_order, period, state)
        elif mode == "salary":
            try:
                await cb.message.delete()
            except:
                pass
            await start_salary_generation(cb.message, inv, prod_order, period, state)
        else:
            pdf_buffer = create_styled_pdf(inv, out, period, mode=mode, product_order=prod_order)
            fname = "Finance_Range.pdf" if mode == "finance" else "Report_Range.pdf"
            await send_pdf(cb.message, pdf_buffer, fname)
            try:
                await cb.message.delete()
            except:
                pass
            await state.clear()
    except Exception as e:
        await cb.message.answer(f"Ошибка: {str(e)}")
        await state.clear()
    

async def main():
    session = AiohttpSession(proxy=PROXY_URL, timeout=300)
    bot = Bot(token=TOKEN, session=session)
    logging.info(f"Бот запущен! Год отчётов: {REPORT_YEAR}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
