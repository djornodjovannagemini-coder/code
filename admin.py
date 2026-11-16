import asyncio
import os
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import database as db
import addin

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
router = Router()

class AdminStates(StatesGroup):
    add_prod_name = State()
    add_prod_desc = State()
    add_prod_price = State()
    add_prod_keys = State()
    ask_broadcast_stock = State()
    broadcast_msg = State()
    edit_screen_text = State()
    edit_screen_photo = State()
    user_balance_id = State()
    user_balance_amount = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ================= ГЛАВНОЕ МЕНЮ АДМИНКИ =================

def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📦 Товары", callback_data="admin:products", style="primary")
    builder.button(text="🎨 Оформление", callback_data="admin:design", style="primary")
    builder.button(text="📢 Рассылка", callback_data="admin:broadcast", style="primary")
    builder.button(text="👥 Пользователи", callback_data="admin:users", style="primary")
    builder.button(text="⬅️ В главное меню", callback_data="menu:back", style="danger", icon_custom_emoji_id="5888484185261216745")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ У вас нет доступа к админке.\nВаш ID: " + str(message.from_user.id))
    await message.answer("🔧 <b>Админ-панель</b>\nВыберите раздел:", reply_markup=admin_main_kb())

@router.callback_query(F.data == "admin:menu")
async def admin_menu(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    try:
        await call.message.edit_caption(caption="🔧 <b>Админ-панель</b>\nВыберите раздел:", reply_markup=admin_main_kb())
    except Exception:
        await call.message.edit_text(text="🔧 <b>Админ-панель</b>\nВыберите раздел:", reply_markup=admin_main_kb())

# ================= УПРАВЛЕНИЕ ТОВАРАМИ =================

def admin_products_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить товар", callback_data="admin:add_prod", style="success")
    builder.button(text="⬅️ Назад", callback_data="admin:menu", style="danger")
    builder.adjust(1, 1)
    return builder.as_markup()

@router.callback_query(F.data == "admin:products")
async def admin_products(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("📦 <b>Управление товарами</b>", reply_markup=admin_products_kb())

@router.callback_query(F.data == "admin:add_prod")
async def start_add_prod(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("1️⃣ Введите название товара (например: Claude 3 Opus):")
    await state.set_state(AdminStates.add_prod_name)

@router.message(AdminStates.add_prod_name)
async def process_prod_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("2️⃣ Введите описание товара:")
    await state.set_state(AdminStates.add_prod_desc)

@router.message(AdminStates.add_prod_desc)
async def process_prod_desc(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("3️⃣ Введите цену в рублях (только число):")
    await state.set_state(AdminStates.add_prod_price)

@router.message(AdminStates.add_prod_price)
async def process_prod_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Ошибка! Введите только число.")
    await state.update_data(price=int(message.text))
    await message.answer("4️⃣ Отправьте API-ключи (каждый с новой строки):")
    await state.set_state(AdminStates.add_prod_keys)

@router.message(AdminStates.add_prod_keys)
async def process_prod_keys(message: Message, state: FSMContext):
    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    if not keys:
        return await message.answer("❌ Вы не отправили ключи. Попробуйте снова.")
        
    data = await state.get_data()
    product_id = await db.add_product(data['name'], data['desc'], data['price'])
    await db.add_product_keys(product_id, keys)
    
    await state.update_data(product_id=product_id, added_qty=len(keys))
    
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, разослать", callback_data="admin:broadcast_stock", style="success")
    kb.button(text="Нет, в меню", callback_data="admin:menu", style="danger")
    
    await message.answer(
        f"✅ Товар <b>{data['name']}</b> добавлен!\nДобавлено ключей: {len(keys)} шт.\n\n"
        f"Сделать рассылку о пополнении всем пользователям?", 
        reply_markup=kb.as_markup()
    )
    await state.set_state(AdminStates.ask_broadcast_stock)

@router.callback_query(F.data == "admin:broadcast_stock")
async def do_stock_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    data = await state.get_data()
    product = await db.get_product(data['product_id'])
    stock = await db.get_product_stock(data['product_id'])
    users = await db.get_all_users_ids()
    
    await call.message.edit_text("⏳ Начинаю рассылку...")
    
    await addin.broadcast_stock_update(
        bot=call.bot, users=users, product_id=data['product_id'],
        product_name=product['name'], added_qty=data['added_qty'],
        total_qty=stock, price=product['price']
    )
    
    await call.message.edit_text("✅ Рассылка завершена!", reply_markup=admin_main_kb())
    await state.clear()

# ================= ОФОРМЛЕНИЕ ЭКРАНОВ =================

def admin_design_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚪 Старт (/start)", callback_data="admin:edit_start", style="primary")
    builder.button(text="👤 Профиль", callback_data="admin:edit_profile", style="primary")
    builder.button(text="🛍 Магазин", callback_data="admin:edit_shop", style="primary")
    builder.button(text="⬅️ Назад", callback_data="admin:menu", style="danger")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()

@router.callback_query(F.data == "admin:design")
async def admin_design(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("🎨 <b>Оформление экранов</b>\nВыберите экран для редактирования:", reply_markup=admin_design_kb())

@router.callback_query(F.data.startswith("admin:edit"))
async def start_edit_screen(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    
    screen = call.data.replace("admin:edit_", "").replace("admin:edit", "")
    
    await state.update_data(screen=screen)
    
    # ИСПРАВЛЕНО: Экранированы скобки &lt; и &gt; для tg-emoji
    text = (
        f"Редактирование экрана <b>{screen}</b>.\n\n"
        f"1️⃣ Отправьте новый текст (HTML и &lt;tg-emoji&gt; поддерживаются).\n"
        f"Если хотите оставить текущий текст, отправьте <code>-</code>."
    )
    
    try:
        await call.message.edit_text(text)
    except Exception as e:
        logging.error(f"Error in start_edit_screen: {e}")
        try:
            await call.message.answer(text)
        except Exception as e2:
            logging.error(f"Error in start_edit_screen fallback: {e2}")
        
    await state.set_state(AdminStates.edit_screen_text)

@router.message(AdminStates.edit_screen_text)
async def process_screen_text(message: Message, state: FSMContext):
    data = await state.get_data()
    screen = data['screen']
    
    text = None if message.text == "-" else message.text
    if text:
        await db.update_screen_setting(screen, text=text)
        
    await message.answer(
        "2️⃣ Отправьте <b>фото (баннер)</b> для этого экрана.\n"
        "Если хотите удалить фото, отправьте <code>0</code>.\n"
        "Если хотите оставить как есть, отправьте <code>-</code>."
    )
    await state.set_state(AdminStates.edit_screen_photo)

@router.message(AdminStates.edit_screen_photo)
async def process_screen_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    screen = data['screen']
    
    if message.text == "-":
        pass
    elif message.text == "0":
        await db.update_screen_setting(screen, photo_id="0")
    elif message.photo:
        photo_id = message.photo[-1].file_id
        await db.update_screen_setting(screen, photo_id=photo_id)
    else:
        return await message.answer("❌ Отправьте фото или 0, или -")
        
    await message.answer(f"✅ Экран <b>{screen}</b> обновлен!", reply_markup=admin_main_kb())
    await state.clear()

# ================= РАССЫЛКА =================

def admin_broadcast_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Создать рассылку", callback_data="admin:do_broadcast", style="success")
    builder.button(text="⬅️ Назад", callback_data="admin:menu", style="danger")
    builder.adjust(1, 1)
    return builder.as_markup()

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(call: CallbackQuery):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("📢 <b>Ручная рассылка</b>\nОтправьте текст, который нужно разослать всем пользователям:", reply_markup=admin_broadcast_kb())

@router.callback_query(F.data == "admin:do_broadcast")
async def start_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("Отправьте сообщение для рассылки (можно с картинкой):")
    await state.set_state(AdminStates.broadcast_msg)

@router.message(AdminStates.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    users = await db.get_all_users_ids()
    await message.answer(f"⏳ Начинаю рассылку на {len(users)} пользователей...")
    
    success = 0
    for uid in users:
        try:
            if message.photo:
                await bot.send_photo(uid, photo=message.photo[-1].file_id, caption=message.caption)
            else:
                await bot.send_message(uid, text=message.text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await message.answer(f"✅ Рассылка завершена!\nДоставлено: {success} из {len(users)}", reply_markup=admin_main_kb())
    await state.clear()

# ================= ПОЛЬЗОВАТЕЛИ =================

@router.callback_query(F.data == "admin:users")
async def admin_users(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not is_admin(call.from_user.id): 
        return
    await call.message.edit_text("👥 Введите ID пользователя, которому нужно изменить баланс:")
    await state.set_state(AdminStates.user_balance_id)

@router.message(AdminStates.user_balance_id)
async def process_user_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ ID должен состоять только из цифр.")
    user = await db.get_user(int(message.text))
    if not user:
        return await message.answer("❌ Пользователь не найден в базе.")
        
    await state.update_data(target_user=int(message.text))
    await message.answer(f"Пользователь: {user['first_name']}\nБаланс: {user['balance']} ₽\n\nВведите сумму для изменения (например: 500 или -100):")
    await state.set_state(AdminStates.user_balance_amount)

@router.message(AdminStates.user_balance_amount)
async def process_user_balance(message: Message, state: FSMContext):
    if not message.text.lstrip('-').isdigit():
        return await message.answer("❌ Введите число.")
        
    amount = int(message.text)
    data = await state.get_data()
    user_id = data['target_user']
    
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await conn.commit()
        
    await message.answer(f"✅ Баланс пользователя <code>{user_id}</code> изменен на {amount} ₽.", reply_markup=admin_main_kb())
    await state.clear()
