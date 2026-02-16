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
from reportlab.lib.pagesizes import A4
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

def parse_any_date(date_str):
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except: return None

def aggregate_data(start_dt, end_dt):
    gc = get_client()
    inventory, out_inv = {}, {}
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        product_map = {row[0].strip(): row[1].strip() for row in sh_p.worksheet("settings_products").get_all_values()[1:] if row[0]}
    except: product_map = {}

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
                else:
                    sec, name_raw, qty_raw, op = r[1].upper(), r[2].strip(), r[3], "IN"

                name = product_map.get(code if sheet_name=="Журнал" else name_raw, name_raw)
                try: qty = float(str(qty_raw).replace(',', '.'))
                except: qty = 0
                
                if "OUT" in op:
                    out_inv[name] = out_inv.get(name, 0) + qty
                else:
                    k = name.upper()
                    inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0})
                    if "1" in sec: inventory[k]["p1"] += qty
                    else: inventory[k]["p2"] += qty
        except Exception as e:
            logging.error(f"Ошибка чтения таблицы {sheet_name}: {e}")
            continue
    return inventory, out_inv

def create_single_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 40

    # Заголовок
    c.setFont(FONT_NAME, 16)
    c.drawCentredString(w/2, h - 50, f"ОТЧЕТ СКЛАДА: {period_text}")
    
    y_start = h - 90
    col_w = (w - margin*2 - 20) / 2

    def draw_table(title, data, x, start_y, bg_color):
        curr_y = start_y
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.setFillColor(colors.HexColor(bg_color))
        c.rect(x, curr_y-18, col_w, 18, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawCentredString(x + col_w/2, curr_y - 13, title)
        
        curr_y -= 18
        total = 0
        c.setFont(FONT_NAME, 9)
        
        if not data:
            c.setStrokeColor(colors.lightgrey)
            c.line(x, curr_y-15, x+col_w, curr_y-15)
            c.drawString(x+5, curr_y-12, "Нет записей")
            curr_y -= 15
        else:
            for name, qty in data:
                c.setStrokeColor(colors.lightgrey)
                c.setLineWidth(0.5)
                c.line(x, curr_y-15, x+col_w, curr_y-15)
                c.drawString(x+3, curr_y-11, name[:45])
                # Формат 1.0 как на скрине
                c.drawRightString(x+col_w-3, curr_y-11, f"{float(qty):.1f}")
                total += qty
                curr_y -= 15
                if curr_y < 100: break # Защита от переполнения

        # Итого секции
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(x, curr_y, x+col_w, curr_y)
        c.setFont(FONT_NAME, 10)
        c.drawString(x+3, curr_y-14, "ИТОГО:")
        c.drawRightString(x+col_w-3, curr_y-14, f"{float(total):.1f}")
        return curr_y - 25, total

    # Данные
    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    outs = sorted([(k, v) for k, v in out_inv.items()])

    # Таблицы
    y_l, s1 = draw_table("ПРИХОД: УЧАСТОК 1", p1, margin, y_start, "#E8F0FE")
    y_l, s2 = draw_table("ПРИХОД: УЧАСТОК 2", p2, margin, y_l, "#E8F0FE")
    y_r, s_out = draw_table("ОТГРУЗКА (OUT)", outs, margin + col_w + 20, y_start, "#FFF2CC")

    # --- ОБЩИЙ ИТОГ (СЕРАЯ ПЛАШКА) ---
    # Фиксируем её внизу страницы
    footer_y = 150 
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.HexColor("#F0F0F0"))
    c.rect(margin, footer_y, w - margin*2, 30, fill=1, stroke=1)
    
    c.setFillColor(colors.black)
    c.setFont(FONT_NAME, 12)
    total_in = float(s1 + s2)
    total_out = float(s_out)
    summary_text = f"ПРИХОД: {total_in:.1f}  |  ОТГРУЗКА: {total_out:.1f}"
    c.drawCentredString(w/2, footer_y + 10, summary_text)

    c.showPage(); c.save(); buffer.seek(0)
    return buffer

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📝 Отчет за сегодня")], [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]], resize_keyboard=True)
    await m.answer("🚀 Бот перезапущен и готов к работе. Дизайн отчета исправлен.", reply_markup=kb)

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    try:
        now = datetime.now()
        inv, out = aggregate_data(now, now)
        pdf = create_single_pdf(inv, out, now.strftime("%d.%m.%Y"))
        await bot.send_document(m.chat.id, BufferedInputFile(pdf.read(), filename=f"Report_{now.strftime('%d_%m')}.pdf"))
    except Exception as e:
        logging.error(f"Ошибка генерации отчета: {e}")
        await m.answer("❌ Произошла ошибка при создании PDF. Проверьте данные в таблицах.")

@dp.message(F.text == "📊 Отчет за день")
async def day_req(m: types.Message):
    await m.answer("Выберите месяц:", reply_markup=get_months_kb("mon_single"))

def get_months_kb(p):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"{p}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)])

def get_days_kb(m, p):
    last = calendar.monthrange(2026, int(m))[1]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(d), callback_data=f"{p}_{d:02d}.{m}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)])

@dp.callback_query(F.data.startswith("mon_single_"))
async def mon_single(cb: types.CallbackQuery):
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(cb.data.split("_")[2], "day_single"))

@dp.callback_query(F.data.startswith("day_single_"))
async def day_finish(cb: types.CallbackQuery):
    d_str = cb.data.split("_")[2]
    dt = datetime.strptime(d_str, "%d.%m.%Y")
    inv, out = aggregate_data(dt, dt)
    pdf = create_single_pdf(inv, out, d_str)
    await bot.send_document(cb.message.chat.id, BufferedInputFile(pdf.read(), filename=f"Report_{d_str}.pdf"))
    await cb.message.delete()

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
