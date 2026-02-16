import asyncio
import io
import calendar
import logging
import re
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession

import gspread
from google.oauth2.service_account import Credentials

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8364799110:AAHZgoSmjBF-C1rnqOyaMeft4VbBoD7Wkys"

ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
ID_PERSONAL = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"
FONT_NAME = "Arial"

logging.basicConfig(level=logging.INFO)
session = AiohttpSession()
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

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

def aggregate_data(start_date, end_date):
    gc = get_client()
    inventory, out_inv = {}, {}
    
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        p_sheet = sh_p.worksheet("settings_products")
        product_map = {row[0].strip(): row[1].strip() for row in p_sheet.get_all_values()[1:] if row[0]}
    except: product_map = {}

    # Чтение из Журнала
    try:
        sh_j = gc.open_by_key(ID_JOURNAL)
        rows = sh_j.worksheet("Журнал").get_all_values()[1:]
        for r in rows:
            if not r or not r[0]: continue
            try:
                row_dt = datetime.strptime(r[0].split()[0], "%d.%m.%Y")
                if not (start_date <= row_dt <= end_date): continue
                code = r[2].strip()
                name = product_map.get(code, r[3].strip() if len(r)>3 and r[3] else code)
                qty = float(r[4].replace(',', '.')) if len(r)>4 and r[4] else 0
                op, sec = r[1].upper(), r[7].upper()
                if "IN" in op or "ORDER" in op:
                    k = name.upper()
                    inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0})
                    if "1" in sec: inventory[k]["p1"] += qty
                    else: inventory[k]["p2"] += qty
                elif "OUT" in op:
                    out_inv[name] = out_inv.get(name, 0) + qty
            except: continue
    except Exception as e: logging.error(f"Ошибка Журнала: {e}")

    # Чтение из Заказов Бота
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        bot_rows = sh_p.worksheet("Заказы_Бот").get_all_values()[1:]
        for br in bot_rows:
            if not br[0]: continue
            try:
                b_dt = datetime.strptime(br[0].split()[0], "%d.%m.%Y")
                if not (start_date <= b_dt <= end_date): continue
                b_name, b_qty = br[2].strip(), float(br[3].replace(',', '.'))
                bk = b_name.upper()
                inventory.setdefault(bk, {"name": b_name, "p1": 0, "p2": 0})
                if "1" in br[1]: inventory[bk]["p1"] += b_qty
                else: inventory[bk]["p2"] += b_qty
            except: continue
    except: pass
    
    return inventory, out_inv

# --- PDF: ОБЫЧНЫЙ ОТЧЕТ (С ОТГРУЗКОЙ) ---
def create_single_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin, gap = 30, 15
    has_out = len(out_inv) > 0
    col_w = (w - (margin*2) - gap)/2 if has_out else (w - margin*2)
    
    c.setFont(FONT_NAME, 14); c.drawCentredString(w/2, h - 35, f"ОТЧЕТ СКЛАДА: {period_text}")
    y_l = y_r = h - 65

    def draw_sec(title, items, color, x, y):
        if not items: return y, 0
        c.setFillColor(colors.HexColor(color)); c.rect(x, y-14, col_w, 14, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setFont(FONT_NAME, 9); c.drawCentredString(x + col_w/2, y-10, title)
        y -= 14; tot = 0; c.setFont(FONT_NAME, 8.5)
        for name, qty in items:
            if y < 40: c.showPage(); y = h - 40; c.setFont(FONT_NAME, 8.5)
            y -= 11; c.drawString(x+3, y+2, name[:45]); c.drawRightString(x+col_w-3, y+2, str(qty))
            c.setStrokeColor(colors.HexColor("#cccccc")); c.setLineWidth(0.3); c.line(x, y, x+col_w, y); tot += qty
        y -= 12; c.setFont(FONT_NAME, 9); c.drawString(x+3, y, "ИТОГО:"); c.drawRightString(x+col_w-3, y, str(tot))
        return y-12, tot

    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    out_items = sorted([(k, v) for k, v in out_inv.items()])

    y_l, s1 = draw_sec("ПРИХОД: УЧАСТОК 1", p1, "#E8F0FE", margin, y_l)
    y_l, s2 = draw_sec("ПРИХОД: УЧАСТОК 2", p2, "#E8F0FE", margin, y_l)
    
    total_out = 0
    if has_out:
        y_r, total_out = draw_sec("ОТГРУЗКА (OUT)", out_items, "#FEEFC3", margin+col_w+gap, y_r)
    
    f_y = max(min(y_l, y_r) - 25, 40)
    c.setFillColor(colors.HexColor("#f3f3f3")); c.rect(margin, f_y-20, w-margin*2, 20, fill=1, stroke=1)
    c.setFillColor(colors.black); c.drawCentredString(w/2, f_y-14, f"ПРИХОД: {int(s1+s2)}  |  ОТГРУЗКА: {int(total_out)}")
    
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- PDF: СРАВНЕНИЕ (СИНХРОННОЕ) ---
def create_comparison_pdf(inv1, inv2, dates_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    w, h = landscape(A4)
    margin, mid_gap = 20, 10
    col_width = (w - (margin*2) - mid_gap) / 2
    
    c.setFont(FONT_NAME, 12); c.drawCentredString(w/2, h - 25, f"СРАВНИТЕЛЬНЫЙ ОТЧЕТ: {dates_text}")
    
    header_y = h - 45
    c.setFillColor(colors.HexColor("#E8F0FE")); c.rect(margin, header_y-15, col_width, 15, fill=1, stroke=1)
    c.rect(margin + col_width + mid_gap, header_y-15, col_width, 15, fill=1, stroke=1)
    c.setFillColor(colors.black); c.setFont(FONT_NAME, 10)
    c.drawCentredString(margin + col_width/2, header_y-11, "ПЕРИОД 1")
    c.drawCentredString(margin + col_width + mid_gap + col_width/2, header_y-11, "ПЕРИОД 2")
    
    y = header_y - 25
    c.setFont(FONT_NAME, 8)
    
    all_keys = sorted(list(set(inv1.keys()) | set(inv2.keys())))
    t1, t2 = 0, 0

    for key in all_keys:
        if y < 30: c.showPage(); y = h - 30; c.setFont(FONT_NAME, 8)
        
        q1 = inv1.get(key, {}).get('p1', 0) + inv1.get(key, {}).get('p2', 0)
        q2 = inv2.get(key, {}).get('p1', 0) + inv2.get(key, {}).get('p2', 0)
        name = inv1.get(key, {}).get('name') or inv2.get(key, {}).get('name') or key
        
        # Период 1
        c.drawString(margin + 2, y, name[:45]); c.drawRightString(margin + col_width - 5, y, str(int(q1)) if q1 > 0 else "-")
        # Период 2
        c.drawString(margin + col_width + mid_gap + 2, y, name[:45]); c.drawRightString(w - margin - 5, y, str(int(q2)) if q2 > 0 else "-")
        
        c.setStrokeColor(colors.HexColor("#e0e0e0")); c.line(margin, y-2, w-margin, y-2)
        t1 += q1; t2 += q2; y -= 12

    c.setFont(FONT_NAME, 10); y -= 10
    c.drawString(margin, y, f"ИТОГО П1: {int(t1)}"); c.drawString(margin + col_width + mid_gap, y, f"ИТОГО П2: {int(t2)}")
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- ХЕНДЛЕРЫ ---
def get_months_kb(prefix):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    kb = [[InlineKeyboardButton(text=m, callback_data=f"{prefix}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_days_kb(month, prefix):
    last = calendar.monthrange(2026, int(month))[1]
    kb = [[InlineKeyboardButton(text=str(d), callback_data=f"{prefix}_{d:02d}.{month}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

comp_data = {}
user_data = {}

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")], 
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")],
        [KeyboardButton(text="⚖️ Сравнить периоды")]
    ], resize_keyboard=True)
    await m.answer("📦 Работаем. Отгрузка возвращена, сравнение активно.", reply_markup=kb)

@dp.message(F.text)
async def handle_text(m: types.Message):
    if m.text == "⚖️ Сравнить периоды":
        comp_data[m.chat.id] = {"stage": 1}
        await m.answer("Период 1 (НАЧАЛО). Месяц:", reply_markup=get_months_kb("cmon"))
    elif m.text == "📝 Отчет за сегодня":
        today = datetime.now().replace(hour=0, minute=0, second=0)
        inv, out = aggregate_data(today, today.replace(hour=23, minute=59))
        pdf = create_single_pdf(inv, out, today.strftime("%d.%m.%Y"))
        await bot.send_document(m.chat.id, BufferedInputFile(pdf.read(), filename="Today.pdf"))
    elif m.text == "📊 Отчет за день":
        await m.answer("Месяц:", reply_markup=get_months_kb("mon_single"))
    elif m.text == "📅 Выбрать промежуток":
        await m.answer("Начало:", reply_markup=get_months_kb("mon_start"))
    else:
        match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', m.text)
        if match:
            try:
                save_order_to_sheet(f"Участок {match.group(2)}", match.group(3).strip(), match.group(4))
                await m.answer("✅")
            except: await m.answer("❌ Ошибка")

@dp.callback_query(F.data.startswith("mon_"))
async def mon_h(cb: types.CallbackQuery):
    _, act, m = cb.data.split("_")
    await cb.message.edit_text("Число:", reply_markup=get_days_kb(m, f"day_{act}"))

@dp.callback_query(F.data.startswith("day_"))
async def day_h(cb: types.CallbackQuery):
    _, act, d = cb.data.split("_"); cid = cb.message.chat.id
    if act == "single":
        dt = datetime.strptime(d, "%d.%m.%Y")
        inv, out = aggregate_data(dt, dt.replace(hour=23, minute=59))
        pdf = create_single_pdf(inv, out, d)
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename=f"Rpt_{d}.pdf"))
    elif act == "start":
        user_data[cid] = d
        await cb.message.edit_text(f"Конец периода. Месяц:", reply_markup=get_months_kb("mon_end"))
    elif act == "end":
        d1, d2 = datetime.strptime(user_data[cid], "%d.%m.%Y"), datetime.strptime(d, "%d.%m.%Y")
        inv, out = aggregate_data(d1, d2)
        pdf = create_single_pdf(inv, out, f"{user_data[cid]}-{d}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Range.pdf"))
    await cb.message.delete()

@dp.callback_query(F.data.startswith("cmon_"))
async def cmon_h(cb: types.CallbackQuery):
    await cb.message.edit_text("Число:", reply_markup=get_days_kb(cb.data.split("_")[1], "cday"))

@dp.callback_query(F.data.startswith("cday_"))
async def cday_h(cb: types.CallbackQuery):
    cid = cb.message.chat.id; d = cb.data.split("_")[1]
    s = comp_data.get(cid, {})
    stage = s.get("stage", 1)
    if stage == 1:
        s["d1"] = d; s["stage"] = 2
        await cb.message.edit_text(f"П1: {d} - ...\nКОНЕЦ П1 (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 2:
        s["d2"] = d; s["stage"] = 3
        await cb.message.edit_text(f"П1: {s['d1']}-{d}\nНАЧАЛО П2 (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 3:
        s["d3"] = d; s["stage"] = 4
        await cb.message.edit_text(f"П2: {d} - ...\nКОНЕЦ П2 (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 4:
        inv1, _ = aggregate_data(datetime.strptime(s["d1"], "%d.%m.%Y"), datetime.strptime(s["d2"], "%d.%m.%Y"))
        inv2, _ = aggregate_data(datetime.strptime(s["d3"], "%d.%m.%Y"), datetime.strptime(d, "%d.%m.%Y"))
        pdf = create_comparison_pdf(inv1, inv2, f"{s['d1']}-{s['d2']} VS {s['d3']}-{d}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Comp.pdf"))
        await cb.message.delete(); comp_data[cid] = {}

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
