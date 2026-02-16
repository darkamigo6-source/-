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

def parse_any_date(date_str):
    """Пытается вытащить дату из любого формата строки"""
    try:
        clean_date = date_str.split()[0].replace(',', '.').strip()
        return datetime.strptime(clean_date, "%d.%m.%Y").date()
    except:
        return None

def aggregate_data(target_date_start, target_date_end):
    gc = get_client()
    inventory, out_inv = {}, {}
    
    # Справочник имен
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        product_map = {row[0].strip(): row[1].strip() for row in sh_p.worksheet("settings_products").get_all_values()[1:] if row[0]}
    except: product_map = {}

    # Поиск по двум таблицам
    for ss_id, sheet_name in [(ID_JOURNAL, "Журнал"), (ID_PERSONAL, "Заказы_Бот")]:
        try:
            sh = gc.open_by_key(ss_id)
            rows = sh.worksheet(sheet_name).get_all_values()[1:]
            for r in rows:
                if not r or not r[0]: continue
                row_date = parse_any_date(r[0])
                if not row_date or not (target_date_start.date() <= row_date <= target_date_end.date()):
                    continue
                
                # Логика колонок
                if sheet_name == "Журнал":
                    code, name_raw, qty_raw, op, sec = r[2].strip(), r[3].strip(), r[4], r[1].upper(), r[7].upper()
                else: # Заказы_Бот: [Дата, Участок, Изделие, Кол-во]
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
            logging.error(f"Ошибка в {sheet_name}: {e}")
            
    return inventory, out_inv

def create_single_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 50

    # Шапка документа
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.5)
    c.line(margin, h-60, w-margin, h-60)
    
    c.setFont(FONT_NAME, 16)
    c.drawString(margin, h-50, "ОТЧЕТ ПО ПРОИЗВОДСТВУ")
    c.setFont(FONT_NAME, 10)
    c.drawRightString(w-margin, h-50, f"Дата: {period_text}")
    
    y = h - 90
    col_w = (w - margin*2 - 20) / 2

    def draw_styled_table(title, items, x, start_y, main_color):
        curr_y = start_y
        # Заголовок секции
        c.setFillColor(main_color)
        c.rect(x, curr_y-20, col_w, 20, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawCentredString(x + col_w/2, curr_y - 14, title)
        
        curr_y -= 20
        # Тело таблицы
        c.setFont(FONT_NAME, 9)
        total = 0
        
        # Отрисовка строк
        if not items:
            c.setStrokeColor(colors.lightgrey)
            c.rect(x, curr_y-20, col_w, 20, fill=0, stroke=1)
            c.drawString(x+10, curr_y-14, "Нет данных за период")
            curr_y -= 20
        else:
            for name, qty in items:
                c.setStrokeColor(colors.lightgrey)
                c.rect(x, curr_y-18, col_w, 18, fill=0, stroke=1)
                c.drawString(x+5, curr_y-13, name[:35])
                c.drawRightString(x+col_w-5, curr_y-13, str(int(qty)) if qty.is_integer() else f"{qty:.1f}")
                total += qty
                curr_y -= 18
                if curr_y < 60:
                    c.showPage(); curr_y = h - 60; c.setFont(FONT_NAME, 9)

        # Итоговая строка
        c.setFillColor(colors.whitesmoke)
        c.rect(x, curr_y-20, col_w, 20, fill=1, stroke=1)
        c.setFillColor(colors.black)
        c.setFont(FONT_NAME, 10)
        c.drawString(x+5, curr_y-14, "ИТОГО:")
        c.drawRightString(x+col_w-5, curr_y-14, str(int(total)))
        return curr_y - 40, total

    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])
    out_data = sorted([(k, v) for k, v in out_inv.items()])

    # Левая сторона (Приход)
    y_l, s1 = draw_styled_table("ПРИХОД: УЧАСТОК 1", p1, margin, y, colors.HexColor("#DDEBFF"))
    y_l, s2 = draw_styled_table("ПРИХОД: УЧАСТОК 2", p2, margin, y_l, colors.HexColor("#DDEBFF"))
    
    # Правая сторона (Отгрузка)
    y_r, s_out = draw_styled_table("ОТГРУЗКА (OUT)", out_data, margin + col_w + 20, y, colors.HexColor("#FFF2CC"))

    # Подпись внизу
    c.setFont(FONT_NAME, 8)
    c.setFillColor(colors.grey)
    c.drawString(margin, 30, f"Сформировано ботом автоматизированного учета склада. {datetime.now().strftime('%H:%M')}")

    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")],
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")],
        [KeyboardButton(text="⚖️ Сравнить периоды")]
    ], resize_keyboard=True)
    await m.answer("📦 Система учета готова. Отчеты теперь в новом формате.", reply_markup=kb)

@dp.message(F.text == "📝 Отчет за сегодня")
async def report_today(m: types.Message):
    wait_msg = await m.answer("⏳ Собираю данные...")
    now = datetime.now()
    inv, out = aggregate_data(now, now)
    pdf = create_single_pdf(inv, out, now.strftime("%d.%m.%Y"))
    await bot.send_document(m.chat.id, BufferedInputFile(pdf.read(), filename=f"Report_{now.strftime('%d_%m')}.pdf"))
    await wait_msg.delete()

# Вспомогательные клавиатуры для дат
def get_months_kb(p):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=m, callback_data=f"{p}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)])

def get_days_kb(m, p):
    last = calendar.monthrange(2026, int(m))[1]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=str(d), callback_data=f"{p}_{d:02d}.{m}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)])

@dp.message(F.text == "📊 Отчет за день")
async def day_req(m: types.Message):
    await m.answer("Выберите месяц:", reply_markup=get_months_kb("mon_single"))

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

# --- Логика записи заказов ---
@dp.message()
async def save_order(m: types.Message):
    match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', m.text)
    if match:
        save_order_to_sheet(f"Участок {match.group(2)}", match.group(3).strip(), match.group(4))
        await m.answer("✅ Записано в вашу таблицу!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
