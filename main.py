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
FONT_NAME = "Arial"
EXCLUDED_CODES = {"OZN15", "OZN11", "OZN13", "OZN12", "OZN14"}

# ====================== ПРОКСИ ======================
PROXY_URL = "socks5://YJvvme:EJBPat@46.8.65.253:8000"
# ===================================================

logging.basicConfig(level=logging.INFO)

dp = Dispatcher(storage=MemoryStorage())

class ReportStates(StatesGroup):
    wait_start_date = State()
    wait_end_date = State()

# --- GOOGLE ---
def get_client():
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_file('creds.json', scopes=scopes)
    return gspread.authorize(creds)

def save_order_to_sheet(sector, name, qty):
    gc = get_client()
    sh = gc.open_by_key(ID_PERSONAL)
    try:
        sheet = sh.worksheet("Заказы_Бот")
    except:
        sheet = sh.add_worksheet(title="Заказы_Бот", rows="100", cols="20")
        sheet.append_row(["Дата", "Участок", "Изделие", "Кол-во"])
    sheet.append_row([datetime.now().strftime("%d.%m.%Y %H:%M:%S"), sector, name, qty])

def parse_any_date(date_str):
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except:
        return None

# --- aggregate_data (твой оригинальный код) ---
def aggregate_data(start_dt, end_dt):
    gc = get_client()
    inventory, out_inv = {}, {}
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        product_map = {row[0].strip(): row[1].strip() for row in sh_p.worksheet("settings_products").get_all_values()[1:] if row[0]}
    except:
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

                name = product_map.get(code if sheet_name=="Журнал" else name_raw, name_raw)
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
                    if "1" in sec_clean:
                        inventory[k]["p1"] += qty
                    elif "2" in sec_clean:
                        inventory[k]["p2"] += qty
        except:
            continue
    return inventory, out_inv

# --- create_single_pdf (твой оригинальный код) ---
def create_single_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 35
    col_w = (w - margin*2 - 15) / 2

    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    outs = sorted([(k, v) for k, v in out_inv.items()])

    sum_p1 = sum(qty for _, qty in p1)
    sum_p2 = sum(qty for _, qty in p2)
    sum_outs = sum(qty for _, qty in outs)
    total_in = sum_p1 + sum_p2

    in_items = []
    if p1:
        in_items += [("HEADER", "ПРИХОД: УЧАСТОК 1", "#E8F0FE")] + p1
        in_items += [("TOTAL_BLOCK", "ИТОГО УЧ. 1:", sum_p1)]
    if p2:
        in_items += [("HEADER", "ПРИХОД: УЧАСТОК 2", "#E8F0FE")] + p2
        in_items += [("TOTAL_BLOCK", "ИТОГО УЧ. 2:", sum_p2)]
       
    out_items = []
    if outs:
        out_items += [("HEADER", "ОТГРУЗКА (OUT)", "#FFF2CC")] + outs
        out_items += [("TOTAL_BLOCK", "ИТОГО ОТГРУЗКА:", sum_outs)]

    def draw_page_framework(page_num):
        c.setFont(FONT_NAME, 14)
        c.drawCentredString(w/2, h - 45, f"ОТЧЕТ СКЛАДА: {period_text} (Стр. {page_num})")
        footer_y = 60
        c.setFillColor(colors.HexColor("#F3F3F3"))
        c.rect(margin, footer_y, w - margin*2, 25, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 11)
        c.drawCentredString(w/2, footer_y + 8, f"ОБЩИЙ ПРИХОД: {float(total_in):.1f} | ОБЩАЯ ОТГРУЗКА: {float(sum_outs):.1f}")

    def draw_column(items, x_pos):
        y_pos = h - 85
        for i, item in enumerate(items):
            if y_pos < 110: return items[i:]
            if item[0] == "HEADER":
                c.setFillColor(colors.HexColor(item[2]))
                c.rect(x_pos, y_pos-16, col_w, 16, fill=1, stroke=1)
                c.setFillColor(colors.black)
                c.setFont(FONT_NAME, 9)
                c.drawCentredString(x_pos + col_w/2, y_pos - 12, item[1])
                y_pos -= 25
            elif item[0] == "TOTAL_BLOCK":
                c.setStrokeColor(colors.black)
                c.setLineWidth(1)
                c.line(x_pos, y_pos-2, x_pos+col_w, y_pos-2)
                c.setFont(FONT_NAME, 9)
                c.drawString(x_pos+3, y_pos-14, item[1])
                c.drawRightString(x_pos+col_w-3, y_pos-14, f"{float(item[2]):.1f}")
                y_pos -= 35
            else:
                name, qty = item
                c.setStrokeColor(colors.HexColor("#DDDDDD"))
                c.setLineWidth(0.5)
                c.line(x_pos, y_pos-12, x_pos+col_w, y_pos-12)
                c.setFillColor(colors.black)
                c.setFont(FONT_NAME, 8.5)
                c.drawString(x_pos+3, y_pos-9, name[:40])
                c.drawRightString(x_pos+col_w-3, y_pos-9, f"{float(qty):.1f}")
                y_pos -= 12
        return []

    page_num = 1
    while in_items or out_items:
        draw_page_framework(page_num)
        if in_items: in_items = draw_column(in_items, margin)
        if out_items: out_items = draw_column(out_items, margin + col_w + 15)
        if in_items or out_items:
            c.showPage()
            page_num += 1
    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- КЛАВИАТУРЫ И ХЕНДЛЕРЫ (всё как было) ---
def get_months_kb(p):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"{p}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)])

def get_days_kb(m, p):
    last = calendar.monthrange(2026, int(m))[1]
    rows = []
    for w in range(1, last + 1, 7):
        row = [InlineKeyboardButton(text=str(d), callback_data=f"{p}_{d:02d}.{m}.2026") for d in range(w, min(w + 7, last + 1))]
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]
    ], resize_keyboard=True)
    await m.answer("📦 Бот готов. Участки теперь считаются раздельно.", reply_markup=kb)

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    n = datetime.now()
    inv, out = aggregate_data(n, n)
    pdf = create_single_pdf(inv, out, n.strftime("%d.%m.%Y"))
    await m.answer_document(BufferedInputFile(pdf.read(), filename="Report_Today.pdf"))

@dp.message(F.text == "📊 Отчет за день")
async def report_day_cmd(m: types.Message):
    await m.answer("Выберите месяц:", reply_markup=get_months_kb("mon_single"))

@dp.message(F.text == "📅 Выбрать промежуток")
async def report_range_cmd(m: types.Message):
    await m.answer("Выберите месяц НАЧАЛА:", reply_markup=get_months_kb("mon_start"))

@dp.callback_query(F.data.startswith("mon_single_"))
async def mon_single(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(m, "day_single"))

@dp.callback_query(F.data.startswith("day_single_"))
async def day_single_finish(cb: types.CallbackQuery):
    d_str = cb.data.split("_")[2]
    dt = datetime.strptime(d_str, "%d.%m.%Y")
    inv, out = aggregate_data(dt, dt)
    pdf = create_single_pdf(inv, out, d_str)
    await cb.message.answer_document(BufferedInputFile(pdf.read(), filename=f"Report_{d_str}.pdf"))
    await cb.message.delete()

@dp.callback_query(F.data.startswith("mon_start_"))
async def mon_start(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Число НАЧАЛА:", reply_markup=get_days_kb(m, "day_start"))

@dp.callback_query(F.data.startswith("day_start_"))
async def day_start_save(cb: types.CallbackQuery, state: FSMContext):
    date_start = cb.data.split("_")[2]
    await state.update_data(start_date=date_start)
    await cb.message.edit_text(f"Начало: {date_start}. Теперь месяц КОНЦА:", reply_markup=get_months_kb("mon_end"))

@dp.callback_query(F.data.startswith("mon_end_"))
async def mon_end(cb: types.CallbackQuery):
    m = cb.data.split("_")[2]
    await cb.message.edit_text("Число КОНЦА:", reply_markup=get_days_kb(m, "day_end"))

@dp.callback_query(F.data.startswith("day_end_"))
async def day_end_finish(cb: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    d1_str, d2_str = data.get("start_date"), cb.data.split("_")[2]
    dt1 = datetime.strptime(d1_str, "%d.%m.%Y")
    dt2 = datetime.strptime(d2_str, "%d.%m.%Y")
    inv, out = aggregate_data(dt1, dt2)
    pdf = create_single_pdf(inv, out, f"{d1_str} - {d2_str}")
    await cb.message.answer_document(BufferedInputFile(pdf.read(), filename="Range_Report.pdf"))
    await cb.message.delete()
    await state.clear()

@dp.message()
async def handle_all(m: types.Message):
    match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', m.text)
    if match:
        save_order_to_sheet(f"Участок {match.group(2)}", match.group(3).strip(), match.group(4))
        await m.answer("✅ Запись добавлена")

# ====================== ЗАПУСК ======================
async def main():
    session = AiohttpSession(proxy=PROXY_URL)          # ← правильный способ
    bot = Bot(token=TOKEN, session=session)
    
    print("✅ Бот запущен с прокси!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
