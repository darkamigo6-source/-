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

# ТАБЛИЦА 1 (ОБЩАЯ - ТОЛЬКО ЧТЕНИЕ ЖУРНАЛА)
ID_JOURNAL = "1QfNVhgoskG-2S0kebjmaUXzl6FbFMuxIfWGioftqRDw"
# ТАБЛИЦА 2 (ТВОЯ - ЗАПИСЬ ЗАКАЗОВ И НАСТРОЙКИ)
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

# --- СОХРАНЕНИЕ ---
def save_order_to_sheet(sector, name, qty):
    gc = get_client()
    sh = gc.open_by_key(ID_PERSONAL)
    try:
        sheet = sh.worksheet("Заказы_Бот")
    except gspread.exceptions.WorksheetNotFound:
        sheet = sh.add_worksheet(title="Заказы_Бот", rows="100", cols="20")
        sheet.append_row(["Дата", "Участок", "Изделие", "Кол-во"])
    
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    sheet.append_row([now, sector, name, qty])

# --- СБОР ДАННЫХ ---
def aggregate_data(start_date, end_date):
    gc = get_client()
    inventory = {} # Формат: {"NAME": {"p1": 0, "p2": 0}}
    
    # 1. Справочник имен (из твоей таблицы)
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        p_sheet = sh_p.worksheet("settings_products")
        product_map = {row[0].strip(): row[1].strip() for row in p_sheet.get_all_values()[1:] if row[0]}
    except: product_map = {}

    # 2. Журнал (Общий)
    try:
        sh_j = gc.open_by_key(ID_JOURNAL)
        journal = sh_j.worksheet("Журнал")
        rows = journal.get_all_values()[1:]
        for r in rows:
            if not r or not r[0]: continue
            try:
                row_dt = datetime.strptime(r[0].split()[0], "%d.%m.%Y")
                if not (start_date <= row_dt <= end_date): continue
                code = r[2].strip()
                name = product_map.get(code, r[3].strip() if len(r)>3 and r[3] else code)
                qty = float(r[4].replace(',', '.')) if len(r)>4 and r[4] else 0
                op, sec = r[1].upper(), r[7].upper()
                
                # Считаем только приход (IN/ORDER)
                if "IN" in op or "ORDER" in op:
                    k = name.upper()
                    inventory.setdefault(k, {"name": name, "p1": 0, "p2": 0})
                    if "1" in sec: inventory[k]["p1"] += qty
                    else: inventory[k]["p2"] += qty
            except: continue
    except: pass

    # 3. Твои заказы
    try:
        sh_p = gc.open_by_key(ID_PERSONAL)
        bot_sheet = sh_p.worksheet("Заказы_Бот")
        bot_rows = bot_sheet.get_all_values()[1:]
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
    
    return inventory

# --- PDF ГЕНЕРАЦИЯ: ОБЫЧНЫЙ ОТЧЕТ ---
def create_single_pdf(inventory, period_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    margin = 30
    col_w = w - margin*2
    
    c.setFont(FONT_NAME, 14)
    c.drawCentredString(w/2, h - 35, f"ОТЧЕТ СКЛАДА: {period_text}")
    
    y = h - 65
    def draw_sec(title, items, color):
        nonlocal y
        if not items: return 0
        c.setFillColor(colors.HexColor(color)); c.rect(margin, y-14, col_w, 14, fill=1, stroke=1)
        c.setFillColor(colors.black); c.setFont(FONT_NAME, 10); c.drawCentredString(w/2, y-10, title)
        y -= 14; tot = 0; c.setFont(FONT_NAME, 9)
        for name, qty in items:
            if y < 40: c.showPage(); y = h - 40; c.setFont(FONT_NAME, 9) # Новая страница
            y -= 12; c.drawString(margin+5, y+2, name[:70]); c.drawRightString(w-margin-5, y+2, str(qty))
            c.setStrokeColor(colors.HexColor("#cccccc")); c.setLineWidth(0.3); c.line(margin, y, w-margin, y); tot += qty
        y -= 15; c.setFont(FONT_NAME, 10); c.drawString(margin+5, y, "ИТОГО:"); c.drawRightString(w-margin-5, y, str(tot))
        y -= 10
        return tot

    p1 = sorted([(v['name'], v['p1']) for v in inventory.values() if v['p1'] > 0])
    p2 = sorted([(v['name'], v['p2']) for v in inventory.values() if v['p2'] > 0])

    s1 = draw_sec("ПРИХОД: УЧАСТОК 1", p1, "#E8F0FE")
    y -= 10
    s2 = draw_sec("ПРИХОД: УЧАСТОК 2", p2, "#E8F0FE")
    
    c.showPage(); c.save(); buffer.seek(0)
    return buffer

# --- PDF ГЕНЕРАЦИЯ: СРАВНЕНИЕ (SIDE-BY-SIDE) ---
def create_comparison_pdf(inv1, inv2, dates_text):
    buffer = io.BytesIO()
    pdfmetrics.registerFont(TTFont(FONT_NAME, "arial.ttf"))
    # Используем Landscape (Альбомная) для ширины
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    w, h = landscape(A4)
    
    margin = 20
    mid_gap = 10
    col_width = (w - (margin*2) - mid_gap) / 2
    
    c.setFont(FONT_NAME, 12)
    c.drawCentredString(w/2, h - 25, f"СРАВНИТЕЛЬНЫЙ ОТЧЕТ: {dates_text}")
    
    # Заголовки колонок
    header_y = h - 45
    c.setFillColor(colors.HexColor("#E8F0FE"))
    c.rect(margin, header_y-15, col_width, 15, fill=1, stroke=1)
    c.rect(margin + col_width + mid_gap, header_y-15, col_width, 15, fill=1, stroke=1)
    
    c.setFillColor(colors.black); c.setFont(FONT_NAME, 10)
    c.drawCentredString(margin + col_width/2, header_y-11, "ПЕРИОД 1 (Слева)")
    c.drawCentredString(margin + col_width + mid_gap + col_width/2, header_y-11, "ПЕРИОД 2 (Справа)")
    
    y = header_y - 25
    c.setFont(FONT_NAME, 8) # Шрифт поменьше, чтобы влезло
    
    # Создаем общий список ключей (товаров), которые были хоть где-то
    all_keys = set(inv1.keys()) | set(inv2.keys())
    sorted_keys = sorted(list(all_keys)) # Алфавитный порядок
    
    total1_p1 = total1_p2 = 0
    total2_p1 = total2_p2 = 0

    for key in sorted_keys:
        if y < 30: # Переход на новую страницу
            c.showPage()
            y = h - 30
            c.setFont(FONT_NAME, 8)
        
        # Данные периода 1
        name1 = inv1.get(key, {}).get('name', '-')
        if name1 == '-': name1 = inv2.get(key, {}).get('name', 'Unknown') # Берем имя из второго, если в первом нет
        
        q1_p1 = inv1.get(key, {}).get('p1', 0)
        q1_p2 = inv1.get(key, {}).get('p2', 0)
        
        # Данные периода 2
        q2_p1 = inv2.get(key, {}).get('p1', 0)
        q2_p2 = inv2.get(key, {}).get('p2', 0)
        
        # Суммируем
        total1_p1 += q1_p1; total1_p2 += q1_p2
        total2_p1 += q2_p1; total2_p2 += q2_p2
        
        # Строка отрисовки
        # Если суммы нули, можно пропустить, или показывать прочерки
        if (q1_p1 + q1_p2 + q2_p1 + q2_p2) == 0: continue

        # ЛЕВАЯ СТОРОНА (Период 1)
        x_left = margin
        txt1 = f"{name1[:40]} [Уч1:{int(q1_p1)} | Уч2:{int(q1_p2)}]"
        val1 = int(q1_p1 + q1_p2)
        if val1 > 0:
            c.drawString(x_left + 2, y, txt1)
            c.drawRightString(x_left + col_width - 5, y, str(val1))
        else:
             c.drawString(x_left + 2, y, name1[:40])
             c.drawRightString(x_left + col_width - 5, y, "-")

        # ПРАВАЯ СТОРОНА (Период 2)
        x_right = margin + col_width + mid_gap
        # Имя справа можно не писать для экономии, но лучше продублировать для наглядности
        # txt2 = f"{name1[:40]}..." 
        # Или просто цифры. Давай просто цифры для чистоты, или имя.
        # ТРЕБОВАНИЕ: "Слева отчет 1, Справа отчет 2". Пишем полностью.
        txt2 = f"{name1[:40]} [Уч1:{int(q2_p1)} | Уч2:{int(q2_p2)}]"
        val2 = int(q2_p1 + q2_p2)
        if val2 > 0:
            c.drawString(x_right + 2, y, txt2)
            c.drawRightString(x_right + col_width - 5, y, str(val2))
        else:
            c.drawString(x_right + 2, y, name1[:40])
            c.drawRightString(x_right + col_width - 5, y, "-")
            
        # Линия
        c.setStrokeColor(colors.HexColor("#e0e0e0"))
        c.line(margin, y-2, w-margin, y-2)
        
        y -= 12

    # ИТОГИ
    y -= 10
    c.setFont(FONT_NAME, 9)
    c.drawString(margin, y, f"ИТОГО ПЕРИОД 1: {int(total1_p1 + total1_p2)}")
    c.drawString(margin + col_width + mid_gap, y, f"ИТОГО ПЕРИОД 2: {int(total2_p1 + total2_p2)}")

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# --- UI & HANDLERS ---
def get_months_kb(prefix):
    months = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
    kb = [[InlineKeyboardButton(text=m, callback_data=f"{prefix}_{i+1:02d}") for i, m in enumerate(months[j:j+3])] for j in range(0, 12, 3)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_days_kb(month, prefix):
    last = calendar.monthrange(2026, int(month))[1]
    kb = [[InlineKeyboardButton(text=str(d), callback_data=f"{prefix}_{d:02d}.{month}.2026") for d in range(w, min(w+7, last+1))] for w in range(1, last+1, 7)]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Состояние для сравнения: {chat_id: {"stage": 1, "d1":..., "d2":..., "d3":...}}
comp_data = {}
user_data = {}

@dp.message(Command("start"))
async def start(m: types.Message):
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Отчет за сегодня")], 
        [KeyboardButton(text="📊 Отчет за день"), KeyboardButton(text="📅 Выбрать промежуток")],
        [KeyboardButton(text="⚖️ Сравнить периоды")]
    ], resize_keyboard=True)
    await m.answer("📦 Меню обновлено. Добавлено сравнение.", reply_markup=kb)

@dp.message(F.text)
async def handle_text(m: types.Message):
    text = m.text.strip()
    cid = m.chat.id
    
    if text == "⚖️ Сравнить периоды":
        comp_data[cid] = {"stage": 1} # 1=Start1, 2=End1, 3=Start2, 4=End2
        await m.answer("ШАГ 1/4. Начало ПЕРВОГО периода. Месяц:", reply_markup=get_months_kb("cmon"))
        return
        
    if text in ["📝 Отчет за сегодня", "📊 Отчет за день", "📅 Выбрать промежуток"]:
        if text == "📝 Отчет за сегодня":
            today = datetime.now().replace(hour=0, minute=0, second=0)
            inv = aggregate_data(today, today.replace(hour=23, minute=59))
            pdf = create_single_pdf(inv, today.strftime("%d.%m.%Y"))
            await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Today.pdf"))
        elif text == "📊 Отчет за день":
            await m.answer("Месяц:", reply_markup=get_months_kb("mon_single"))
        elif text == "📅 Выбрать промежуток":
            await m.answer("Начало:", reply_markup=get_months_kb("mon_start"))
        return

    # Заказы
    match = re.search(r'(?i)(участ(?:ок|-к)?\s*(\d+))\s+(.+)\s+(\d+)$', text)
    if match:
        s, n, q = f"Участок {match.group(2)}", match.group(3).strip(), match.group(4)
        try:
            save_order_to_sheet(s, n, q)
            await m.answer(f"✅ ПРИНЯТО")
        except Exception as e: await m.answer(f"❌ Ошибка: {e}")
    else:
        await m.answer("⚠️ Неверный формат.")

# --- CALLBACKS ОБЫЧНЫЕ ---
@dp.callback_query(F.data.startswith("mon_"))
async def mon_h(cb: types.CallbackQuery):
    _, act, m = cb.data.split("_")
    await cb.message.edit_text("Число:", reply_markup=get_days_kb(m, f"day_{act}"))

@dp.callback_query(F.data.startswith("day_"))
async def day_h(cb: types.CallbackQuery):
    _, act, d = cb.data.split("_"); cid = cb.message.chat.id
    if act == "single":
        dt = datetime.strptime(d, "%d.%m.%Y")
        inv = aggregate_data(dt, dt.replace(hour=23, minute=59))
        pdf = create_single_pdf(inv, d)
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename=f"Rpt_{d}.pdf"))
        await cb.message.delete()
    elif act == "start":
        user_data[cid] = d
        await cb.message.edit_text(f"Начало: {d}\nКонец. Месяц:", reply_markup=get_months_kb("mon_end"))
    elif act == "end":
        s = user_data.get(cid)
        d1, d2 = datetime.strptime(s, "%d.%m.%Y"), datetime.strptime(d, "%d.%m.%Y")
        inv = aggregate_data(d1, d2)
        pdf = create_single_pdf(inv, f"{s}-{d}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Range.pdf"))
        await cb.message.delete()

# --- CALLBACKS ДЛЯ СРАВНЕНИЯ ---
@dp.callback_query(F.data.startswith("cmon_"))
async def cmon_h(cb: types.CallbackQuery):
    _, m = cb.data.split("_")
    await cb.message.edit_text("Выберите число:", reply_markup=get_days_kb(m, "cday"))

@dp.callback_query(F.data.startswith("cday_"))
async def cday_h(cb: types.CallbackQuery):
    _, d = cb.data.split("_"); cid = cb.message.chat.id
    state = comp_data.get(cid, {})
    stage = state.get("stage", 1)
    
    if stage == 1:
        state["d1"] = d; state["stage"] = 2
        await cb.message.edit_text(f"📅 Период 1: {d} - ...\nВыберите КОНЕЦ первого периода (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 2:
        state["d2"] = d; state["stage"] = 3
        await cb.message.edit_text(f"📅 Период 1: {state['d1']} - {d}\n\nШАГ 3/4. Начало ВТОРОГО периода (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 3:
        state["d3"] = d; state["stage"] = 4
        await cb.message.edit_text(f"📅 Период 2: {d} - ...\nВыберите КОНЕЦ второго периода (Месяц):", reply_markup=get_months_kb("cmon"))
    elif stage == 4:
        d4 = d
        d1, d2 = datetime.strptime(state["d1"], "%d.%m.%Y"), datetime.strptime(state["d2"], "%d.%m.%Y")
        d3, d4_dt = datetime.strptime(state["d3"], "%d.%m.%Y"), datetime.strptime(d4, "%d.%m.%Y")
        
        await cb.message.edit_text("⏳ Генерирую сравнительный отчет...")
        
        # Сбор данных
        inv1 = aggregate_data(d1, d2)
        inv2 = aggregate_data(d3, d4_dt)
        
        # PDF
        pdf = create_comparison_pdf(inv1, inv2, f"{state['d1']}-{state['d2']} VS {state['d3']}-{d4}")
        await bot.send_document(cid, BufferedInputFile(pdf.read(), filename="Comparison.pdf"))
        comp_data[cid] = {} # Сброс

async def main(): await dp.start_polling(bot)
if __name__ == "__main__": asyncio.run(main())
