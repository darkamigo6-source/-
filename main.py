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

# ТАБЛИЦА 1 (ОТКУДА БЕРЕМ ЖУРНАЛ)
SOURCE_SS_ID_1 = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
# ТАБЛИЦА 2 (КУДА ПИШЕМ ЗАКАЗЫ И ГДЕ НАСТРОЙКИ ТОВАРОВ)
SOURCE_SS_ID_2 = "1YBLY5ZBedRcalgdmXzTqsiVwQXP75LXnZ6bZlNYKIbY"

FONT_NAME = "Arial"

logging.basicConfig(level=logging.INFO)
session = AiohttpSession()
bot = Bot(token=TOKEN, session=session)
dp = Dispatcher()

# --- ФУНКЦИЯ ПОДКЛЮЧЕНИЯ ---
def get_client():
    scopes = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file('creds.json', scopes=scopes)
    return gspread.authorize(creds)

# --- СОХРАНЕНИЕ ЗАКАЗА (ТОЛЬКО В ТАБЛИЦУ 2) ---
def save_order_to_sheet(sector, name, qty):
    gc = get_client()
    sh = gc.open_by_key(SOURCE_SS_ID_2)
    try:
        sheet = sh.worksheet("Заказы_Бот")
    except gspread.exceptions.WorksheetNotFound:
        sheet = sh.add_worksheet(title="Заказы_Бот", rows="100", cols="20")
        sheet.append_row(["Дата", "Участок", "Изделие", "Кол-во"])
    
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    sheet.append_row([now, sector, name, qty])

# --- СБОР ДАННЫХ ИЗ ДВУХ ТАБЛИЦ ДЛЯ ОТЧЕТА ---
def aggregate_data(start_date, end_date):
    gc = get_client()
    inventory, out_inv = {}, {}

    # 1. Загружаем названия товаров из Таблицы 2 (Лист settings_products)
    try:
        sh2 = gc.open_by_key(SOURCE_SS_ID_2)
        p_sheet = sh2.worksheet("settings_products")
        product_map = {row[0].strip(): row[1].strip() for row in p_sheet.get_all_values()[1:] if row[0]}
    except: 
        product_map = {}

    # 2. Читаем основной "Журнал" из Таблицы 1
    try:
        sh1 = gc.open_by_key(SOURCE_SS_ID_1)
        journal = sh1.worksheet("Журнал")
        rows = journal.get_all_values()[1:]
        for r in rows:
            if not r or not r[0]: continue
            try:
                row_dt = datetime.strptime(r[0].split()[0], "%d.%m.%Y")
                if not (start_date <= row_dt <= end_date): continue
                
                code = r[2].strip()
                if code in ["OZN11", "OZN12", "OZN13", "OZN14", "OZN15"]: continue
                
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
    except Exception as e: 
        logging.error(f"Ошибка Таблицы 1: {e}")

    # 3. Добавляем ручные заказы из Таблицы 2 (Лист Заказы_Бот)
    try:
        bot_sheet = sh2.worksheet("Заказы_Бот")
        bot_rows = bot_sheet.get_all_values()[1:]
        for br in bot_rows:
            if not br[0]: continue
            try:
                b_dt = datetime.strptime(br[0].split()[0], "%d.%m.%Y")
                if not (start_date <= b_dt <= end_date): continue
                
                b_name = br[2].strip()
                b_qty = float(br[3].replace(',', '.'))
                bk = b_name.upper()
                
                inventory.setdefault(bk, {"name": b_name, "p1": 0, "p2": 0})
                if "1" in br[1]: inventory[bk]["p1"] += b_qty
                else: inventory[bk]["p2"] += b_qty
            except: continue
    except: 
        pass
    
    return inventory, out_inv

# --- ГЕНЕРАЦИЯ PDF ---
def create_styled_pdf(inventory, out_inv, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
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
            y -= 11; c.drawString(x+3, y+2, name[:45]); c.drawRightString(x+col_w-3, y+2, str(qty))
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
    kb = [[InlineKeyboardButton(text=m, callback_data=f"mon_{action}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_days_kb(month, action):
    last = calendar.monthrange(2026, int(month))[1]
    kb = [[InlineKeyboardButton(text=str(d), callback_data=f"day_{action}_{d:02d}.{month}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

user_data = {}

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📝 Отчет за сегодня")], [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")]], resize_keyboard=True)
    await m.answer("📦 Система ПАК МЕБЕЛЬ активна.\n\nПишите заказ в формате:\n`Участок 1 Название 10`", reply_markup=kb)

@dp.message(F.text)
async def handle_text_messages(m: types.Message):
    text = m.text.strip()
    
    # Кнопки меню
    if text in ["📝 Отчет за сегодня", "📊 Отчет за день", "📅 Выбрать промежуток"]:
        if text == "📝 Отчет за сегодня":
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            inv, out = aggregate_data(today, today.replace(hour=23, minute=59))
            pdf = create_styled_pdf(inv, out, today.strftime("%d.%m.%Y"))
            await bot.send_document(m.chat.id, BufferedInputFile(pdf.read(), filename="Today.pdf"))
        elif text == "📊 Отчет за день":
            await m.answer("Выберите МЕСЯЦ:", reply_markup=get_months_kb("single"))
        elif text == "📅 Выбрать промежуток":
            await m.answer("Начало периода. Выберите МЕСЯЦ:", reply_markup=get_months_kb("start"))
        return

    # РАЗБОР ЗАКАЗА: Участок [номер] [название] [количество]
    match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', text)
    if match:
        full_sector = f"Участок {match.group(2)}"
        product_name = match.group(3).strip()
        quantity = match.group(4)
        
        try:
            save_order_to_sheet(full_sector, product_name, quantity)
            await m.answer(f"✅ ПРИНЯТО В ТАБЛИЦУ 2:\n📍 {full_sector}\n📦 {product_name}\n🔢 Кол-во: {quantity}")
        except Exception as e:
            await m.answer(f"❌ Ошибка записи (403): Проверь доступ e-mail к Таблице 2!\n{e}")
    else:
        await m.answer("⚠️ Не понял формат. Пишите так:\n`Участок 1 Название товара 10`")

# --- CALLBACKS ДЛЯ КАЛЕНДАРЯ ---
@dp.callback_query(F.data.startswith("mon_"))
async def sel_mon(cb: types.CallbackQuery):
    _, action, m_num = cb.data.split("_")
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(m_num, action))

@dp.callback_query(F.data.startswith("day_"))
async def sel_day(cb: types.CallbackQuery):
    _, action, d_str = cb.data.split("_")
    cid = cb.message.chat.id
    if action == "single":
        dt = datetime.strptime(d_str, "%d.%m.%Y")
        inv, out = aggregate_data(dt, dt.replace(hour=23, minute=59))
        pdf = create_styled_pdf(inv, out, d_str)
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename=f"Report_{d_str}.pdf"))
        await cb.message.delete()
    elif action == "start":
        user_data[cid] = d_str
        await cb.message.edit_text(f"📍 С: {d_str}\nВыберите месяц конца:", reply_markup=get_months_kb("end"))
    elif action == "end":
        start_d = user_data.get(cid)
        d1, d2 = datetime.strptime(start_d, "%d.%m.%Y"), datetime.strptime(d_str, "%d.%m.%Y")
        inv, out = aggregate_data(d1, d2)
        pdf = create_styled_pdf(inv, out, f"{start_d}-{d_str}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Range_Report.pdf"))
        await cb.message.delete()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
