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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# ====================== НАСТРОЙКИ ======================
TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"
ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
ID_PERSONAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
ADMIN_ID = 766046065  # <--- ВСТАВЬ СЮДА СВОЙ TELEGRAM ID
FONT_NAME = "Arial"
EXCLUDED_CODES = {"OZN15", "OZN11", "OZN13", "OZN12", "OZN14"}
PROXY_URL = "socks5://XpptV2:QwwjXk@138.219.120.129:9926"

logging.basicConfig(level=logging.INFO)
dp = Dispatcher(storage=MemoryStorage())

class ReportStates(StatesGroup):
    wait_start_date = State()
    wait_end_date = State()

# --- GOOGLE FUNCTIONS ---
def get_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('creds.json', scopes=scopes)
    return gspread.authorize(creds)

def get_product_settings():
    """Возвращает маппинг: {код: {'name': имя, 'price': цена}}"""
    gc = get_client()
    sh = gc.open_by_key(ID_PERSONAL)
    try:
        rows = sh.worksheet("settings_products").get_all_values()[1:]
        mapping = {}
        for r in rows:
            if not r[0]: continue
            try:
                price = float(str(r[2]).replace(',', '.').strip())
            except:
                price = 0.0
            mapping[r[0].strip()] = {"name": r[1].strip(), "price": price}
        return mapping
    except:
        return {}

def aggregate_data(start_dt, end_dt, is_finance=False):
    gc = get_client()
    inventory = {}
    product_map = get_product_settings()

    for ss_id, sheet_name in [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]: continue
                row_date = parse_any_date(r[0])
                if not row_date or not (start_dt.date() <= row_date <= end_dt.date()): continue
                
                # Логика определения операции
                if sheet_name == "Журнал":
                    code, name_raw, qty_raw, op, sec = r[2].strip(), r[3].strip(), r[4], r[1].upper(), r[7].upper()
                    if code in EXCLUDED_CODES or name_raw in EXCLUDED_CODES: continue
                    # Для финансов берем только приход (IN), если это Журнал
                    if is_finance and "OUT" in op: continue
                else:
                    sec, name_raw, qty_raw, op = r[1].upper(), r[2].strip(), r[3], "IN"
                    if name_raw in EXCLUDED_CODES: continue

                # Маппинг данных
                key = code if sheet_name=="Журнал" else name_raw
                meta = product_map.get(key)
                
                if not meta:
                    return f"Критическая ошибка: Изделие '{name_raw}' (Код: {key}) отсутствует в справочнике!", None

                if is_finance and meta['price'] <= 0:
                    return f"Ошибка: Для '{meta['name']}' не указана себестоимость в таблице!", None

                try:
                    qty = float(str(qty_raw).replace(',', '.'))
                except:
                    qty = 0
                
                k = meta['name'].upper()
                inventory.setdefault(k, {"name": meta['name'], "qty": 0, "price": meta['price']})
                inventory[k]["qty"] += qty
        except Exception as e:
            logging.error(f"Ошибка в цикле агрегации: {e}")
            continue
            
    return inventory, None

def parse_any_date(date_str):
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except:
        return None

# --- PDF GENERATION ---
def create_finance_pdf(inventory, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 40
    
    c.setFont(FONT_NAME, 14)
    c.drawCentredString(w/2, h - 50, f"ФИНАНСОВЫЙ ОТЧЕТ (СЕБЕСТОИМОСТЬ): {period_text}")
    
    y = h - 100
    c.setFont(FONT_NAME, 10)
    # Заголовки таблицы
    headers = ["Наименование", "Кол-во", "Цена ед.", "Сумма"]
    x_positions = [margin, 350, 420, 500]
    
    for txt, x in zip(headers, x_positions):
        c.drawString(x, y, txt)
    
    y -= 20
    total_sum = 0
    
    items = sorted(inventory.values(), key=lambda x: x['name'])
    for item in items:
        if y < 80:
            c.showPage()
            y = h - 50
            c.setFont(FONT_NAME, 10)

        subtotal = item['qty'] * item['price']
        total_sum += subtotal
        
        c.setFont(FONT_NAME, 8)
        c.drawString(x_positions[0], y, item['name'][:55])
        c.drawRightString(x_positions[1] + 30, y, f"{item['qty']:.1f}")
        c.drawRightString(x_positions[2] + 40, y, f"{item['price']:.2f}")
        c.drawRightString(x_positions[3] + 45, y, f"{subtotal:.2f}")
        
        c.setStrokeColor(colors.lightgrey)
        c.line(margin, y-2, w-margin, y-2)
        y -= 15

    y -= 20
    c.setFont(FONT_WEIGHT="bold", psName=FONT_NAME, size=12)
    c.drawRightString(w - margin, y, f"ОБЩАЯ СЕБЕСТОИМОСТЬ: {total_sum:,.2f} руб.")
    
    c.save()
    buffer.seek(0)
    return buffer

# --- HANDLERS ---
@dp.message(Command("finance"))
async def finance_cmd(m: types.Message):
    if m.from_user.id != ADMIN_ID:
        await m.answer("⛔ У вас нет прав для просмотра финансовых отчетов.")
        return
    await m.answer("Выберите месяц для ФИНАНСОВОГО отчета:", reply_markup=get_months_kb("fin_mon"))

@dp.callback_query(F.data.startswith("fin_mon_"))
async def fin_month_selected(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Выберите число начала периода:", reply_markup=get_days_kb(m, "fin_start"))

@dp.callback_query(F.data.startswith("fin_start_"))
async def fin_start_selected(cb: types.CallbackQuery, state: FSMContext):
    date_start = cb.data.split("_")[2]
    await state.update_data(start_date=date_start)
    await cb.message.edit_text(f"Начало: {date_start}. Теперь месяц КОНЦА:", reply_markup=get_months_kb("fin_end"))

@dp.callback_query(F.data.startswith("fin_end_"))
async def fin_end_selected(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Число КОНЦА периода:", reply_markup=get_days_kb(m, "fin_done"))

@dp.callback_query(F.data.startswith("fin_done_"))
async def fin_final(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    d1_str, d2_str = data.get("start_date"), cb.data.split("_")[2]
    dt1 = datetime.strptime(d1_str, "%d.%m.%Y")
    dt2 = datetime.strptime(d2_str, "%d.%m.%Y")
    
    await cb.message.edit_text("⏳ Считаю деньги, подождите...")
    
    result, error = aggregate_data(dt1, dt2, is_finance=True)
    
    if error:
        await cb.message.answer(error)
        await state.clear()
        return

    pdf = create_finance_pdf(result, f"{d1_str} - {d2_str}")
    await cb.message.answer_document(BufferedInputFile(pdf.read(), filename=f"Finance_Report_{d1_str}.pdf"))
    await state.clear()

# (Остальные хендлеры и клавиатуры из твоего старого кода оставить без изменений)
# Не забудь добавить функции get_months_kb и get_days_kb ниже!

# ====================== ЗАПУСК ======================
async def main():
    session = AiohttpSession(proxy=PROXY_URL, timeout=180)
    bot = Bot(token=TOKEN, session=session)
    print("✅ Финансовый бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
