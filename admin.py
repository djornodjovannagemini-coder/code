import asyncio
import os
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiosqlite # Оставил для совместимости, но используем db

import database as db
import addin

logger = logging.getLogger(__name__)

# ЖЕСТКАЯ ОЧИСТКА ID
raw_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
logger.info(f"🔑 Загруженные ID админов: {ADMIN_IDS}")

router = Router()

def is_adm(uid): return uid in ADMIN_IDS

class Adm(StatesGroup):
    # Товары
    p_name = State(); p_desc = State(); p_price = State(); p_type = State(); p_items = State()
    # Юзеры
    u_id = State(); u_amount = State()
    # Оформление
    d_text = State(); d_photo = State()
    # Рассылка
    b_msg = State()

# ================= ГЛАВНОЕ МЕНЮ =================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    logger.info(f"Получена команда /admin от {message.from_user.id}")
    if not is_adm(message.from_user.id):
        return await message.answer(f"⛔ У вас нет доступа.\nВаш ID: <code>{message.from_user.id}</code>\nID в базе: <code>{ADMIN_IDS}</code>")
    try:
        await message.answer("🔧 <b>Админ-панель</b>", reply_markup=addin.admin_main_kb())
    except Exception as e:
        logger.error(f"Ошибка при открытии админки: {e}")

@router.callback_query(F.data == "adm:menu")
async def adm_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    if not is_adm(call.from_user.id): return
    try: 
        await call.message.edit_text("🔧 <b>Админ-панель</b>", reply_markup=addin.admin_main_kb())
    except: 
        await call.message.answer("🔧 <b>Админ-панель</b>", reply_markup=addin.admin_main_kb())

# ================= 1. ТОВАРЫ =================
@router.callback_query(F.data == "adm:prod")
async def adm_prod(call: CallbackQuery):
    await call.answer()
    if is_adm(call.from_user.id): 
        await call.message.edit_text("📦 <b>Управление товарами</b>", reply_markup=addin.admin_products_kb())

@router.callback_query(F.data == "adm:prod:add")
async def add_p1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("1️⃣ Введите название товара:")
    await state.set_state(Adm.p_name)

@router.message(Adm.p_name)
async def add_p2(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("2️⃣ Введите описание:")
    await state.set_state(Adm.p_desc)

@router.message(Adm.p_desc)
async def add_p3(msg: Message, state: FSMContext):
    await state.update_data(desc=msg.text)
    await msg.answer("3️⃣ Введите цену (число):")
    await state.set_state(Adm.p_price)

@router.message(Adm.p_price)
async def add_p4(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("❌ Только число!")
    await state.update_data(price=int(msg.text))
    kb = InlineKeyboardBuilder()
    kb.button(text="Текст/Ключ", callback_data="p_type_text")
    kb.button(text="Ссылка", callback_data="p_type_link")
    kb.button(text="Файл", callback_data="p_type_file")
    await msg.answer("4️⃣ Выберите тип товара:", reply_markup=kb.as_markup())
    await state.set_state(Adm.p_type)

@router.callback_query(Adm.p_type)
async def add_p5(call: CallbackQuery, state: FSMContext):
    await call.answer()
    p_type = call.data.replace("p_type_", "")
    await state.update_data(type=p_type)
    await call.message.edit_text("5️⃣ Отправьте содержимое (текст, ссылку или файл):")
    await state.set_state(Adm.p_items)

@router.message(Adm.p_items)
async def add_p6(msg: Message, state: FSMContext):
    data = await state.get_data()
    items = []
    if msg.document: items = [msg.document.file_id]
    elif msg.text: items = [x.strip() for x in msg.text.split("\n") if x.strip()]
    else: return await msg.answer("❌ Неверный формат.")
    
    pid = await db.add_product(data['name'], data['desc'], data['price'], data['type'])
    await db.add_product_items(pid, items)
    await msg.answer(f"✅ Товар <b>{data['name']}</b> добавлен! ({len(items)} шт.)", reply_markup=addin.admin_main_kb())
    await state.clear()

@router.callback_query(F.data == "adm:prod:toggle")
async def toggle_p(call: CallbackQuery):
    await call.answer("Функция в разработке. Скоро будет список.", show_alert=True)

# ================= 2. ЮЗЕРЫ =================
@router.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery):
    await call.answer()
    if is_adm(call.from_user.id): 
        await call.message.edit_text("👥 <b>Пользователи</b>", reply_markup=addin.admin_users_kb())

@router.callback_query(F.data == "adm:users:bal")
async def u_bal1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Введите Telegram ID пользователя:")
    await state.set_state(Adm.u_id)

@router.message(Adm.u_id)
async def u_bal2(msg: Message, state: FSMContext):
    if not msg.text.isdigit(): return await msg.answer("❌ ID - это число.")
    user = await db.get_user(int(msg.text))
    if not user: return await msg.answer("❌ Не найден.")
    await state.update_data(uid=int(msg.text))
    await msg.answer(f"Юзер: {user['first_name']}\nБаланс: {user['balance']} ₽\n\nВведите сумму (+500 или -100):")
    await state.set_state(Adm.u_amount)

@router.message(Adm.u_amount)
async def u_bal3(msg: Message, state: FSMContext):
    if not msg.text.lstrip('-').isdigit(): return await msg.answer("❌ Только число.")
    amt = int(msg.text)
    data = await state.get_data()
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amt, data['uid'])
    await msg.answer(f"✅ Баланс изменен на {amt} ₽.", reply_markup=addin.admin_main_kb())
    await state.clear()

# ================= 3-5. ЗАКАЗЫ, ПРОМО, РАССЫЛКА =================
@router.callback_query(F.data == "adm:orders")
async def adm_orders(call: CallbackQuery):
    await call.answer("🧾 Раздел в разработке", show_alert=True)

@router.callback_query(F.data == "adm:promos")
async def adm_promos(call: CallbackQuery):
    await call.answer("🎟 Раздел в разработке", show_alert=True)

@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_adm(call.from_user.id): return
    await call.message.edit_text("📢 Отправьте сообщение для рассылки (текст или фото):")
    await state.set_state(Adm.b_msg)

@router.message(Adm.b_msg)
async def do_broadcast(msg: Message, state: FSMContext, bot: Bot):
    users = await db.get_all_users_ids()
    await msg.answer(f"⏳ Начинаю рассылку на {len(users)} юзеров...")
    count = 0
    for uid in users:
        try:
            if msg.photo: await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption)
            else: await bot.send_message(uid, msg.text)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await msg.answer(f"✅ Доставлено: {count}/{len(users)}", reply_markup=addin.admin_main_kb())
    await state.clear()

# ================= 6. ОФОРМЛЕНИЕ =================
@router.callback_query(F.data == "adm:design")
async def adm_design(call: CallbackQuery):
    await call.answer()
    if is_adm(call.from_user.id): 
        await call.message.edit_text("🎨 <b>Оформление</b>", reply_markup=addin.admin_design_kb())

@router.callback_query(F.data.startswith("adm:design:"))
async def design_screen(call: CallbackQuery):
    await call.answer()
    screen = call.data.split(":")[2]
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Текст экрана", callback_data=f"adm:ed:t:{screen}", style="primary")
    kb.button(text="🖼 Картинка", callback_data=f"adm:ed:p:{screen}", style="primary")
    kb.button(text="⬅️ Назад", callback_data="adm:design", style="danger")
    kb.adjust(1, 1, 1)
    await call.message.edit_text(f"Настройка экрана <b>{screen}</b>:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("adm:ed:t:"))
async def edit_text_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen)
    await call.message.edit_text(f"Отправьте новый текст для <b>{screen}</b>.\nЕсли хотите оставить старый, отправьте <code>-</code>.")
    await state.set_state(Adm.d_text)

@router.message(Adm.d_text)
async def process_new_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    screen = data['screen']
    
    if msg.text == "-":
        await msg.answer("Текст оставлен без изменений.")
    else:
        new_text = msg.text or msg.caption or ""
        if msg.entities:
            for entity in msg.entities:
                if entity.type == "custom_emoji":
                    emoji_char = new_text[entity.offset:entity.offset + entity.length]
                    new_text = new_text.replace(emoji_char, f'<tg-emoji emoji-id="{entity.custom_emoji_id}">{emoji_char}</tg-emoji>', 1)
        await db.set_setting(f"{screen}_text", new_text)
        await msg.answer("✅ Текст обновлен!")
        
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="adm:design", style="danger")
    await msg.answer("Вернуться в меню?", reply_markup=kb.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("adm:ed:p:"))
async def edit_photo_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen)
    await call.message.edit_text(f"Отправьте новое фото для <b>{screen}</b> (или <code>0</code> для удаления):")
    await state.set_state(Adm.d_photo)

@router.message(Adm.d_photo)
async def process_new_photo(msg: Message, state: FSMContext):
    data = await state.get_data()
    screen = data['screen']
    
    if msg.text == "0":
        await db.set_setting(f"{screen}_photo", "")
        await msg.answer("Фото удалено.")
    elif msg.photo:
        await db.set_setting(f"{screen}_photo", msg.photo[-1].file_id)
        await msg.answer("✅ Фото обновлено!")
    else:
        await msg.answer("❌ Отправьте фото или 0.")
        return
        
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="adm:design", style="danger")
    await msg.answer("Вернуться в меню?", reply_markup=kb.as_markup())
    await state.clear()

# ================= 7. НАСТРОЙКИ =================
@router.callback_query(F.data == "adm:settings")
async def adm_settings(call: CallbackQuery):
    await call.answer()
    tw = await db.get_setting("tech_work", "0")
    await call.message.edit_text("⚙️ <b>Настройки</b>", reply_markup=addin.admin_settings_kb(tw))

@router.callback_query(F.data == "adm:settings:tech")
async def toggle_tech(call: CallbackQuery):
    await call.answer("Режим тех.работ переключен!")
    tw = await db.get_setting("tech_work", "0")
    new_tw = "1" if tw == "0" else "0"
    await db.set_setting("tech_work", new_tw)
    await call.message.edit_reply_markup(reply_markup=addin.admin_settings_kb(new_tw))

# ================= 8-10. СТАТИСТИКА, ФИНАНСЫ, СИСТЕМА =================
@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    await call.answer()
    s = await db.get_stats()
    text = f"📊 <b>Статистика</b>\n━━━━━━━━━━━━━\n👥 Юзеров: <b>{s['users']}</b>\n🧾 Заказов: <b>{s['orders']}</b>\n💰 Продаж: <b>{s['sales']} ₽</b>"
    await call.message.edit_text(text, reply_markup=addin.admin_back_kb())

@router.callback_query(F.data == "adm:finance")
async def adm_finance(call: CallbackQuery):
    await call.answer("💳 Раздел в разработке", show_alert=True)

@router.callback_query(F.data == "adm:system")
async def adm_system(call: CallbackQuery):
    await call.answer("🛡 Раздел в разработке", show_alert=True)
