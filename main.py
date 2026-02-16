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
bot = Bot(token=TOKEN, session=AiohttpSession())
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

# --- СБОР ДАННЫХ (УЛУЧШЕННЫЙ) ---
def aggregate_data(start_date, end_date):
    gc = get_client()
    inventory, out_inv = {}, {}
    
    # 1. Справочник
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        product_map = {row[0].strip(): row[1].strip() for row in sh_p.worksheet("settings_products").get_all_values()[1:] if row[0]}
    except: product_map = {}

    # 2. Чтение из двух источников
    sources = [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]
    
    for ss_id, sheet_name in sources:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]: continue
                try:
                    # Чистим дату от лишних пробелов и берем только день
                    raw_date = r[0].split()[0].replace(',', '.').strip()
                    row_dt = datetime.strptime(raw_date, "%d.%m.%Y")
                    
                    if not (start_date.date() <= row_dt.date() <= end_date.date()): continue
                    
                    # Для Журнала (8 колонок), для Заказов Бота (4 колонки)
                    if sheet_name == "Журнал":
                        code, name_raw, qty_raw, op, sec = r[2].strip(), r[3].strip(), r[4], r[1].upper(), r[7].upper()
                    else:
                        sec, name_raw, qty_raw, op = r[1].upper(), r[2].strip(), r[3], "IN", r[1].upper()

                    name = product_map.get(code if sheet_name=="Журнал" else name_raw, name_raw)
                    qty = float(str(qty_raw).replace(',', '.')) if qty_raw else 0
                    
                    if "OUT" in op:
                        out_inv[name] = out_inv.get(name, 0) + qty
                    else:
                        k = name.upper()
                        inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0})
                        if "1" in sec: inventory[k]["p1"] += qty
                        else: inventory[k]["p2"] += qty
                except: continue
        except: continue
        
    return inventory, out_inv

# --- КРАСИВЫЙ PDF (УЛУЧШЕННЫЙ ВИЗУАЛ) ---
def create_single_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 40
    
    # Заголовок
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(w/2, h - 50, "ОТЧЕТ ПО СКЛАДУ")
    c.setFont(FONT_NAME, 10)
    c.drawCentredString(w/2, h - 65, f"Период: {period_text}")

    y = h - 100
    col_w = (w - margin*2 - 20) / 2

    def draw_table(title, data, x, start_y, color_hex):
        curr_y = start_y
        # Шапка таблицы
        c.setStrokeColor(colors.black)
        c.setFillColor(colors.HexColor(color_hex))
        c.rect(x, curr_y, col_w, 18, fill=1)
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawCentredString(x + col_w/2, curr_y + 5, title)
        
        curr_y -= 15
        c.setFont(FONT_NAME, 9)
        total = 0
        
        if not data:
            c.drawCentredString(x + col_w/2, curr_y - 10, "Нет данных")
            return curr_y - 30, 0

        for name, qty in data:
            if curr_y < 50: # Перенос
                c.showPage(); curr_y = h - 50; c.setFont(FONT_NAME, 9)
            
            # Строка
            c.setLineWidth(0.5)
            c.setStrokeColor(colors.HexColor("#D3D3D3"))
            c.line(x, curr_y, x + col_w, curr_y)
            
            c.drawString(x + 5, curr_y + 3, name[:35])
            c.drawRightString(x + col_w - 5, curr_y + 3, str(int(qty)) if qty.is_integer() else str(qty))
            
            total += qty
            curr_y -= 15
            
        # Итоговая линия
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(x, curr_y, x + col_w, curr_y)
        c.setFont(FONT_NAME, 9)
        c.drawString(x + 5, curr_y - 12, "ИТОГО:")
        c.drawRightString(x + col_w - 5, curr_y - 12, str(int(total)))
        
        return curr_y - 30, total

    # Подготовка
    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    out_items = sorted([(k, v) for k, v in out_inv.items()])

    # Рисуем
    y_left, s1 = draw_table("ПРИХОД: УЧАСТОК 1", p1, margin, y, "#E8F0FE")
    y_left, s2 = draw_table("ПРИХОД: УЧАСТОК 2", p2, margin, y_left, "#E8F0FE")
    
    y_right, s_out = draw_table("ОТГРУЗКА (OUT)", out_items, margin + col_w + 20, y, "#FFF2CC")

    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- ОСТАЛЬНОЙ КОД (СРАВНЕНИЕ И ХЕНДЛЕРЫ) ---
def create_comparison_pdf(inv1, inv2, dates_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    w, h = landscape(A4)
    margin = 30
    c.setFont(FONT_NAME, 14); c.drawCentredString(w/2, h - 40, f"СРАВНЕНИЕ: {dates_text}")
    
    col_w = (w - margin*2 - 20) / 2
    y = h - 70
    
    # Заголовки
    c.setFillColor(colors.HexColor("#F0F0F0")); c.rect(margin, y, col_w, 20, fill=1); c.rect(margin+col_w+20, y, col_w, 20, fill=1)
    c.setFillColor(colors.black); c.setFont(FONT_NAME, 10)
    c.drawCentredString(margin + col_w/2, y+6, "ПЕРИОД 1"); c.drawCentredString(margin+col_w+20 + col_w/2, y+6, "ПЕРИОД 2")
    
    y -= 20
    all_keys = sorted(list(set(inv1.keys()) | set(inv2.keys())))
    for k in all_keys:
        if y < 40: c.showPage(); y = h - 40
        q1 = inv1.get(k, {}).get('p1', 0) + inv1.get(k, {}).get('p2', 0)
        q2 = inv2.get(k, {}).get('p1', 0) + inv2.get(k, {}).get('p2', 0)
        name = inv1.get(k, {}).get('name') or inv2.get(k, {}).get('name') or k
        
        c.setFont(FONT_NAME, 8)
        c.drawString(margin+5, y, name[:45]); c.drawRightString(margin+col_w-5, y, str(int(q1)) if q1>0 else "-")
        c.drawString(margin+col_w+25, y, name[:45]); c.drawRightString(w-margin-5, y, str(int(q2)) if q2>0 else "-")
        c.setStrokeColor(colors.lightgrey); c.line(margin, y-2, w-margin, y-2)
        y -= 12

    c.showPage(); c.save(); buffer.seek(0)
    return buffer

user_data, comp_data = {}, {}

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📝 Отчет за сегодня")], [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")], [KeyboardButton(text="⚖️ Сравнить периоды")]], resize_keyboard=True)
    await m.answer("📦 Система обновлена. Визуал подправлен.", reply_markup=kb)

@dp.message(F.text)
async def handle_text(m: types.Message):
    cid = m.chat.id
    if m.text == "📝 Отчет за сегодня":
        now = datetime.now()
        inv, out = aggregate_data(now, now)
        pdf = create_single_pdf(inv, out, now.strftime("%d.%m.%Y"))
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Today.pdf"))
    elif m.text == "⚖️ Сравнить периоды":
        comp_data[cid] = {"stage": 1}
        await m.answer("П1 (Начало). Месяц:", reply_markup=get_months_kb("cmon"))
    elif m.text == "📊 Отчет за день":
        await m.answer("Месяц:", reply_markup=get_months_kb("mon_single"))
    elif m.text == "📅 Выбрать промежуток":
        await m.answer("Начало:", reply_markup=get_months_kb("mon_start"))
    else:
        match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', m.text)
        if match:
            save_order_to_sheet(f"Участок {match.group(2)}", match.group(3).strip(), match.group(4))
            await m.answer("✅")

def get_months_kb(p):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"{p}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)])

def get_days_kb(m, p):
    last = calendar.monthrange(2026, int(m))[1]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(d), callback_data=f"{p}_{d:02d}.{m}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)])

@dp.callback_query(F.data.startswith("mon_"))
async def mon_h(cb: types.CallbackQuery):
    _, a, m = cb.data.split("_"); await cb.message.edit_text("Число:", reply_markup=get_days_kb(m, f"day_{a}"))

@dp.callback_query(F.data.startswith("day_"))
async def day_h(cb: types.CallbackQuery):
    _, a, d = cb.data.split("_"); cid = cb.message.chat.id
    dt = datetime.strptime(d, "%d.%m.%Y")
    if a == "single":
        inv, out = aggregate_data(dt, dt)
        pdf = create_single_pdf(inv, out, d)
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename=f"Rpt_{d}.pdf"))
    elif a == "start":
        user_data[cid] = d; await cb.message.edit_text(f"Конец. Месяц:", reply_markup=get_months_kb("mon_end"))
    elif a == "end":
        d1 = datetime.strptime(user_data[cid], "%d.%m.%Y")
        inv, out = aggregate_data(d1, dt)
        pdf = create_single_pdf(inv, out, f"{user_data[cid]}-{d}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Range.pdf"))
    await cb.message.delete()

@dp.callback_query(F.data.startswith("cmon_"))
async def cmon_h(cb: types.CallbackQuery):
    await cb.message.edit_text("Число:", reply_markup=get_days_kb(cb.data.split("_")[1], "cday"))

@dp.callback_query(F.data.startswith("cday_"))
async def cday_h(cb: types.CallbackQuery):
    cid, d = cb.message.chat.id, cb.data.split("_")[1]
    s = comp_data.get(cid, {})
    if s.get("stage") == 1:
        s["d1"] = d; s["stage"] = 2; await cb.message.edit_text(f"П1: {d}-...\nКонец П1:", reply_markup=get_months_kb("cmon"))
    elif s.get("stage") == 2:
        s["d2"] = d; s["stage"] = 3; await cb.message.edit_text(f"П1 закончен. П2 Начало:", reply_markup=get_months_kb("cmon"))
    elif s.get("stage") == 3:
        s["d3"] = d; s["stage"] = 4; await cb.message.edit_text(f"П2: {d}-...\nКонец П2:", reply_markup=get_months_kb("cmon"))
    elif s.get("stage") == 4:
        inv1, _ = aggregate_data(datetime.strptime(s["d1"], "%d.%m.%Y"), datetime.strptime(s["d2"], "%d.%m.%Y"))
        inv2, _ = aggregate_data(datetime.strptime(s["d3"], "%d.%m.%Y"), datetime.strptime(d, "%d.%m.%Y"))
        pdf = create_comparison_pdf(inv1, inv2, f"{s['d1']} vs {d}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Comp.pdf"))
        await cb.message.delete(); comp_data[cid] = {}

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
