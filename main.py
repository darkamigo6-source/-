import asyncio
import io
import calendar
import logging
import re
from datetime import datetime

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
from reportlab.lib import colors

# ====================== НАСТРОЙКИ (ПРОВЕРЬ ИХ!) ======================
TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"
ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
ID_PERSONAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
ADMIN_ID = 766046065  # <--- ОБЯЗАТЕЛЬНО ВСТАВЬ СВОЙ ID СЮДА
EXCLUDED_CODES = {"OZN15", "OZN11", "OZN13", "OZN12", "OZN14"}
PROXY_URL = "socks5://XpptV2:QwwjXk@138.219.120.129:9926"

logging.basicConfig(level=logging.INFO)
dp = Dispatcher(storage=MemoryStorage())

# --- GOOGLE FUNCTIONS ---
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

# --- ГЛАВНАЯ ФУНКЦИЯ (ТВОЯ + МОИ ПРАВКИ ПО ЦЕНАМ) ---
def aggregate_data(start_dt, end_dt, is_finance=False):
    gc = get_client()
    inventory, out_inv = {}, {}
    
    # Загружаем справочник цен и имен
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        # Собираем {Код: (Имя, Цена)}
        product_rows = sh_p.worksheet("settings_products").get_all_values()[1:]
        product_map = {}
        for r in product_rows:
            if not r[0]: continue
            try:
                price = float(str(r[2]).replace(',', '.').strip()) if len(r) > 2 else 0.0
            except:
                price = 0.0
            product_map[r[0].strip()] = {"name": r[1].strip(), "price": price}
    except Exception as e:
        logging.error(f"Ошибка справочника: {e}")
        product_map = {}

    for ss_id, sheet_name in [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]: continue
                row_date = parse_any_date(r[0])
                if not row_date or not (start_dt.date() <= row_date <= end_dt.date()): continue
                
                if sheet_name == "Журнал":
                    code, name_raw, qty_raw, op, sec = r[2].strip(), r[3].strip(), r[4], r[1].upper(), r[7].upper()
                    if code in EXCLUDED_CODES or name_raw in EXCLUDED_CODES: continue
                else:
                    sec, name_raw, qty_raw, op = r[1].upper(), r[2].strip(), r[3], "IN"
                    if name_raw in EXCLUDED_CODES: continue

                # Получаем данные из нашего справочника
                key = code if sheet_name=="Журнал" else name_raw
                meta = product_map.get(key, {"name": name_raw, "price": 0.0})
                name = meta["name"]
                price = meta["price"]

                try:
                    qty = float(str(qty_raw).replace(',', '.'))
                except:
                    qty = 0
                
                if "OUT" in op:
                    if not is_finance: # В финансовом отчете OUT не нужен по твоему ТЗ
                        out_inv[name] = out_inv.get(name, 0) + qty
                else:
                    k = name.upper()
                    inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0, "price": price})
                    sec_clean = str(sec).upper()
                    if "1" in sec_clean: inventory[k]["p1"] += qty
                    elif "2" in sec_clean: inventory[k]["p2"] += qty
        except:
            continue
    return inventory, out_inv

# --- ПРОСТОЙ PDF (БЕЗ ВНЕШНИХ ШРИФТОВ) ---
def create_report_pdf(inventory, out_inv, period_text, is_finance=False):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    # Используем Helvetica — она встроена в PDF и не требует файлов .ttf
    c.setFont("Helvetica", 12) 
    
    title = "FINANCE REPORT" if is_finance else "STOCK REPORT"
    c.drawCentredString(300, 800, f"{title}: {period_text}")
    
    y = 750
    total_finance = 0
    
    for item in inventory.values():
        total_qty = item['p1'] + item['p2']
        if total_qty <= 0: continue
        
        line = f"{item['name']} | Qty: {total_qty}"
        if is_finance:
            subtotal = total_qty * item['price']
            total_finance += subtotal
            line += f" | Price: {item['price']} | Total: {subtotal}"
        
        c.drawString(50, y, line)
        y -= 20
        if y < 50:
            c.showPage()
            y = 800

    if is_finance:
        y -= 20
        c.drawString(50, y, f"TOTAL SUM: {total_finance} RUB")

    c.save()
    buffer.seek(0)
    return buffer

# --- ХЕНДЛЕРЫ (ТВОИ ОРИГИНАЛЬНЫЕ) ---
@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")],
        [KeyboardButton(text="💰 Финансы (Админ)")] # Добавили кнопку
    ], resize_keyboard=True)
    await m.answer("📦 Бот запущен и готов к работе.", reply_markup=kb)

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    n = datetime.now()
    inv, out = aggregate_data(n, n)
    pdf = create_report_pdf(inv, out, n.strftime("%d.%m.%Y"))
    await m.answer_document(BufferedInputFile(pdf.read(), filename="Report.pdf"))

@dp.message(F.text == "💰 Финансы (Админ)")
async def finance_check(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        await m.answer("Доступ запрещен.")
        return
    n = datetime.now()
    inv, out = aggregate_data(n, n, is_finance=True)
    pdf = create_report_pdf(inv, out, n.strftime("%d.%m.%Y"), is_finance=True)
    await m.answer_document(BufferedInputFile(pdf.read(), filename="Finance.pdf"))

# --- ОСТАЛЬНАЯ ЛОГИКА (БЕЗ ИЗМЕНЕНИЙ) ---
# ... (Добавь сюда свои хендлеры выбора даты и запуск бота как в оригинале)

async def main():
    session = AiohttpSession(proxy=PROXY_URL, timeout=180)
    bot = Bot(token=TOKEN, session=session)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
