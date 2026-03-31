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

# ====================== НАСТРОЙКИ ======================
TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"
ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
ID_PERSONAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
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

def parse_any_date(date_str):
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except:
        return None

def aggregate_data(start_dt, end_dt):
    gc = get_client()
    inventory = {}
    out_inv = {}

    for ss_id, sheet_name in [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]: continue
                row_date = parse_any_date(r[0])
                if not row_date or not (start_dt.date() <= row_date <= end_dt.date()): continue
                
                if sheet_name == "Журнал":
                    code, name, qty_raw, op, sec = r[2].strip(), r[3].strip(), r[4], r[1].upper(), r[7].upper()
                    if code in EXCLUDED_CODES or name in EXCLUDED_CODES: continue
                else:
                    sec, name, qty_raw, op = r[1].upper(), r[2].strip(), r[3], "IN"
                    if name in EXCLUDED_CODES: continue

                try:
                    qty = float(str(qty_raw).replace(',', '.'))
                except:
                    qty = 0
                
                if "OUT" in op:
                    out_inv[name] = out_inv.get(name, 0) + qty
                else:
                    k = name.upper()
                    inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0})
                    sec_clean = str(sec).upper()
                    if "1" in sec_clean: inventory[k]["p1"] += qty
                    elif "2" in sec_clean: inventory[k]["p2"] += qty
        except:
            continue
            
    return inventory, out_inv

# --- PDF GENERATION ---
def create_report_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    
    c.setFont(FONT_NAME, 14)
    c.drawCentredString(w/2, h - 50, f"ОТЧЕТ ПО СКЛАДУ: {period_text}")
    
    y = h - 100
    c.setFont(FONT_NAME, 10)
    
    items = sorted(inventory.values(), key=lambda x: x['name'])
    for item in items:
        if y < 80:
            c.showPage()
            y = h - 50
            c.setFont(FONT_NAME, 10)
            
        total = item['p1'] + item['p2']
        line = f"{item['name']} — Всего: {total} (Уп1: {item['p1']}, Уп2: {item['p2']})"
        c.drawString(50, y, line)
        y -= 20
        
    if out_inv:
        y -= 20
        c.setFont(FONT_NAME, 12)
        c.drawString(50, y, "ОТГРУЖЕНО (OUT):")
        y -= 20
        c.setFont(FONT_NAME, 10)
        for name, q in sorted(out_inv.items()):
            c.drawString(60, y, f"{name}: {q}")
            y -= 15
            
    c.save()
    buffer.seek(0)
    return buffer

# --- KEYBOARDS ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]
    ], resize_keyboard=True)

def get_months_kb(prefix):
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    months = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
    for i, m in enumerate(months, 1):
        kb.inline_keyboard.append([InlineKeyboardButton(text=m, callback_query_data=f"{prefix}_{i:02d}")])
    return kb

def get_days_kb(month, prefix):
    kb = InlineKeyboardMarkup(inline_keyboard=[[]])
    now = datetime.now()
    _, last_day = calendar.monthrange(now.year, int(month))
    for d in range(1, last_day + 1):
        if len(kb.inline_keyboard[-1]) >= 7: kb.inline_keyboard.append([])
        date_str = f"{d:02d}.{month}.{now.year}"
        kb.inline_keyboard[-1].append(InlineKeyboardButton(text=str(d), callback_query_data=f"{prefix}_{date_str}"))
    return kb

# --- HANDLERS ---
@dp.message(Command("start"))
async def start(m: types.Message):
    await m.answer("📦 Бот готов к работе.", reply_markup=main_kb())

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    n = datetime.now()
    inv, out = aggregate_data(n, n)
    pdf = create_report_pdf(inv, out, n.strftime("%d.%m.%Y"))
    await m.answer_document(BufferedInputFile(pdf.read(), filename="Today.pdf"))

@dp.message(F.text == "📊 Отчет за день")
async def report_day(m: types.Message):
    await m.answer("Выберите месяц:", reply_markup=get_months_kb("day_mon"))

@dp.callback_query(F.data.startswith("day_mon_"))
async def month_selected(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(m, "day_done"))

@dp.callback_query(F.data.startswith("day_done_"))
async def day_final(cb: types.CallbackQuery):
    d_str = cb.data.split("_")[2]
    dt = datetime.strptime(d_str, "%d.%m.%Y")
    inv, out = aggregate_data(dt, dt)
    pdf = create_report_pdf(inv, out, d_str)
    await cb.message.answer_document(BufferedInputFile(pdf.read(), filename=f"Report_{d_str}.pdf"))

@dp.message(F.text == "📅 Выбрать промежуток")
async def range_start(m: types.Message):
    await m.answer("Месяц НАЧАЛА:", reply_markup=get_months_kb("rng_st_mon"))

@dp.callback_query(F.data.startswith("rng_st_mon_"))
async def rng_st_month(cb: types.CallbackQuery):
    m = cb.data.split("_")[3]
    await cb.message.edit_text("Число НАЧАЛА:", reply_markup=get_days_kb(m, "rng_st_done"))

@dp.callback_query(F.data.startswith("rng_st_done_"))
async def rng_st_final(cb: types.CallbackQuery, state: FSMContext):
    await state.update_data(start_date=cb.data.split("_")[3])
    await cb.message.edit_text("Месяц КОНЦА:", reply_markup=get_months_kb("rng_en_mon"))

@dp.callback_query(F.data.startswith("rng_en_mon_"))
async def rng_en_month(cb: types.CallbackQuery):
    m = cb.data.split("_")[3]
    await cb.message.edit_text("Число КОНЦА:", reply_markup=get_days_kb(m, "rng_en_done"))

@dp.callback_query(F.data.startswith("rng_en_done_"))
async def rng_final(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    d1_str, d2_str = data['start_date'], cb.data.split("_")[3]
    dt1, dt2 = datetime.strptime(d1_str, "%d.%m.%Y"), datetime.strptime(d2_str, "%d.%m.%Y")
    inv, out = aggregate_data(dt1, dt2)
    pdf = create_report_pdf(inv, out, f"{d1_str}-{d2_str}")
    await cb.message.answer_document(BufferedInputFile(pdf.read(), filename="Range.pdf"))
    await state.clear()

async def main():
    session = AiohttpSession(proxy=PROXY_URL)
    bot = Bot(token=TOKEN, session=session)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
