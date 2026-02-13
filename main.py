import asyncio
import io
import calendar
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession

import gspread
from google.oauth2.service_account import Credentials

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# Логирование
logging.basicConfig(level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"
SOURCE_SS_ID = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
FONT_NAME = "Arial"

try:
    pdfmetrics.registerFont(TTFont(FONT_NAME, "Arial.ttf"))
except:
    print("❌ ШРИФТ Arial.ttf НЕ НАЙДЕН!")

# ИСУПРАВЛЕНИЕ: Используем простой таймаут (число), чтобы избежать TypeError
session = AiohttpSession()
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

# Google Sheets
creds = Credentials.from_service_account_file('creds.json', scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive'])
gc = gspread.authorize(creds)

# --- СБОР ДАННЫХ ---
def aggregate_data(start_date, end_date):
    sh = gc.open_by_key(SOURCE_SS_ID)
    try:
        p_sheet = sh.worksheet("settings_products")
        product_map = {row[0].strip(): row[1].strip() for row in p_sheet.get_all_values()[1:] if row[0]}
    except: product_map = {}

    inventory, out_inv = {}, {}
    journal = sh.worksheet("Журнал")
    rows = journal.get_all_values()[1:]
    
    for r in rows:
        if not r or len(r) < 5 or not r[0]: continue
        try:
            row_dt = datetime.strptime(r[0].split()[0], "%d.%m.%Y")
            if not (start_date <= row_dt <= end_date): continue
            
            code = r[2].strip()
            if code in ["OZN11", "OZN12", "OZN13", "OZN14", "OZN15"]: continue
            
            name = product_map.get(code, r[3].strip() if len(r) > 3 and r[3] else code)
            qty_str = r[4].replace(',', '.') if len(r) > 4 else "0"
            qty = float(qty_str) if qty_str else 0
            
            op = r[1].upper() if len(r) > 1 else ""
            sec = r[7].upper() if len(r) > 7 else ""
            
            if "IN" in op or "ORDER" in op:
                k = name.upper()
                if k not in inventory: inventory[k] = {"name": name, "p1": 0, "p2": 0}
                if "1" in sec: inventory[k]["p1"] += qty
                else: inventory[k]["p2"] += qty
            elif "OUT" in op:
                out_inv[name] = out_inv.get(name, 0) + qty
        except Exception: continue
    return inventory, out_inv

# --- ПДФ ---
def create_styled_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin, gap = 30, 15
    has_out = len(out_inv) > 0
    col_w = (w - (margin*2) - gap)/2 if has_out else (w - margin*2)

    c.setFont(FONT_NAME, 14)
    c.drawCentredString(w/2, h - 35, f"ОТЧЕТ СКЛАДА: {period_text}")
    y_l = y_r = h - 65

    def draw_sec(title, items, color, x, y):
        if not items: return y, 0
        c.setFillColor(colors.HexColor(color)); c.rect(x, y-14, col_w, 14, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setFont(FONT_NAME, 9); c.drawCentredString(x + col_w/2, y-10, title)
        y -= 14; tot = 0; c.setFont(FONT_NAME, 8.5)
        for name, qty in items:
            y -= 11
            if y < 40: # Переход на новую страницу если тесно
                c.showPage()
                y = h - 40
            c.drawString(x+3, y+2, name[:45]); c.drawRightString(x+col_w-3, y+2, str(qty))
            c.setStrokeColor(colors.HexColor("#cccccc")); c.setLineWidth(0.3); c.line(x, y, x+col_w, y); tot += qty
        y -= 12; c.setFont(FONT_NAME, 9); c.drawString(x+3, y, "ИТОГО:"); c.drawRightString(x+col_w-3, y, str(tot))
        return y-12, tot

    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    out = sorted([(k, v) for k, v in out_inv.items()])

    y_l, s1 = draw_sec("ПРИХОД: УЧАСТОК 1", p1, "#E8F0FE", margin, y_l)
    y_l, s2 = draw_sec("ПРИХОД: УЧАСТОК 2", p2, "#E8F0FE", margin, y_l)
    total_out = 0
    if has_out:
        y_r, total_out = draw_sec("ОТГРУЗКА (OUT)", out, "#FEEFC3", margin+col_w+gap, y_r)

    f_y = max(min(y_l, y_r) - 25, 40)
    c.setFillColor(colors.HexColor("#f3f3f3")); c.rect(margin, f_y-20, w-margin*2, 20, fill=1, stroke=1)
    c.setFillColor(colors.black); c.drawCentredString(w/2, f_y-14, f"ПРИХОД: {s1+s2}  |  ОТГРУЗКА: {total_out}")
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- КАЛЕНДАРЬ ---
def get_months_kb(action):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    kb = []
    row = []
    for i, m in enumerate(months, 1):
        row.append(InlineKeyboardButton(text=m, callback_data=f"mon_{action}_{i:02d}"))
        if len(row) == 3: kb.append(row); row = []
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_days_kb(month, action):
    kb = []
    last = calendar.monthrange(2026, int(month))[1]
    row = []
    for d in range(1, last + 1):
        row.append(InlineKeyboardButton(text=str(d), callback_data=f"day_{action}_{d:02d}.{month}.2026"))
        if len(row) == 7: kb.append(row); row = []
    if row: kb.append(row)
    return InlineKeyboardMarkup(inline_keyboard=kb)

user_data = {}

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]
    ], resize_keyboard=True)
    await m.answer("📦 Складской бот запущен.", reply_markup=kb)

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    wait = await m.answer("⏳ Минутку, считаю сегодня...")
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        inv, out = aggregate_data(today, today.replace(hour=23, minute=59))
        pdf = create_styled_pdf(inv, out, today.strftime("%d.%m.%Y"))
        await bot.send_document(m.chat.id, BufferedInputFile(pdf.read(), filename=f"Today.pdf"))
    except Exception as e:
        await m.answer(f"Ошибка: {e}")
    finally: await wait.delete()

@dp.message(F.text == "📊 Отчет за день")
async def one_day_report(m: types.Message):
    await m.answer("Выберите МЕСЯЦ:", reply_markup=get_months_kb("single"))

@dp.message(F.text == "📅 Выбрать промежуток")
async def range_report(m: types.Message):
    await m.answer("📅 Начало. Выберите МЕСЯЦ:", reply_markup=get_months_kb("start"))

@dp.callback_query(F.data.startswith("mon_"))
async def sel_mon(cb: types.CallbackQuery):
    _, action, m_num = cb.data.split("_")
    await cb.message.edit_text("Теперь выберите ЧИСЛО:", reply_markup=get_days_kb(m_num, action))

@dp.callback_query(F.data.startswith("day_"))
async def sel_day(cb: types.CallbackQuery):
    _, action, d_str = cb.data.split("_")
    cid = cb.message.chat.id
    
    if action == "single":
        wait = await cb.message.answer(f"⏳ Считаю за {d_str}...")
        try:
            dt = datetime.strptime(d_str, "%d.%m.%Y")
            inv, out = aggregate_data(dt, dt.replace(hour=23, minute=59))
            pdf = create_styled_pdf(inv, out, d_str)
            await bot.send_document(cid, BufferedInputFile(pdf.read(), filename=f"Report_{d_str}.pdf"))
        finally: 
            await wait.delete()
            await cb.message.delete()

    elif action == "start":
        user_data[cid] = d_str
        await cb.message.edit_text(f"📍 Начало: {d_str}\nВыберите МЕСЯЦ конца:", reply_markup=get_months_kb("end"))

    elif action == "end":
        start_d = user_data.get(cid)
        wait = await cb.message.answer(f"⏳ Собираю период {start_d} - {d_str}...")
        try:
            d1, d2 = datetime.strptime(start_d, "%d.%m.%Y"), datetime.strptime(d_str, "%d.%m.%Y")
            inv, out = aggregate_data(d1, d2)
            pdf = create_styled_pdf(inv, out, f"{start_d}-{d_str}")
            await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Report.pdf"))
        finally:
            user_data.pop(cid, None)
            await wait.delete()
            await cb.message.delete()

async def main():
    # Явно указываем таймаут при запуске поллинга
    await dp.start_polling(bot, request_timeout=300)

if __name__ == "__main__":
    asyncio.run(main())