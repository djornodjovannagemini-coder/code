import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from dotenv import load_dotenv

import admin
import addin
import database as db

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    await db.register_user(user_id, message.from_user.first_name, message.from_user.username)
    
    # Получаем данные юзера для баланса
    user = await db.get_user(user_id)
    balance = user['balance'] if user else 0
    
    settings = await db.get_screen_settings("start")
    text = settings.get("text", "Привет! Добро пожаловать.")
    
    # Заменяем плейсхолдеры
    text = text.replace("{name}", message.from_user.first_name or "друг")
    text = text.replace("{balance}", str(balance))
    
    photo = settings.get("photo_id")
    kb = addin.main_menu_kb(settings)
    
    if photo:
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.answer(text=text, reply_markup=kb)

@router.callback_query(F.data == "menu:profile")
async def show_profile(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if not user:
        return await call.answer("Ошибка. Напишите /start", show_alert=True)
        
    settings = await db.get_screen_settings("profile")
    text = settings.get("text", "Профиль")
    
    try:
        text = text.format(
            name=call.from_user.first_name or "друг",
            balance=user['balance'],
            spent=user['total_spent'],
            purchases=user['purchases_count'],
            refs=user['ref_count'],
            ref_earned=user['ref_earned'],
            user_id=user['user_id']
        )
    except KeyError:
        pass
        
    photo = settings.get("photo_id")
    kb = addin.profile_kb(settings)
    
    try:
        if photo:
            await call.message.edit_media(media=addin.InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
        else:
            await call.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        if photo:
            await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else:
            await call.message.answer(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "menu:shop")
async def show_shop(call: CallbackQuery):
    settings = await db.get_screen_settings("shop")
    text = settings.get("text", "Магазин")
    photo = settings.get("photo_id")
    kb = addin.shop_menu_kb(settings)
    
    try:
        if photo:
            await call.message.edit_media(media=addin.InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
        else:
            await call.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        if photo:
            await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else:
            await call.message.answer(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "shop:api")
async def show_products(call: CallbackQuery):
    products = await db.get_active_products()
    if not products:
        return await call.answer("Товаров пока нет 😔", show_alert=True)
        
    settings = await db.get_screen_settings("catalog")
    text = settings.get("text", "Выберите товар:")
    
    kb = addin.products_list_kb(products)
    
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    except Exception:
        await call.message.edit_text(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("shop:product:"))
async def show_product_card(call: CallbackQuery):
    product_id = int(call.data.split(":")[2])
    product = await db.get_product(product_id)
    stock = await db.get_product_stock(product_id)
    
    if not product:
        return await call.answer("Товар не найден", show_alert=True)
        
    text = (
        f"{product['name']}\n"
        f"━━━━━━━━━━━━━\n\n"
        f"{product['description']}\n\n"
        f"💰 Цена: <b>{product['price']} ₽</b>\n"
        f"📦 В наличии: <b>{stock} шт.</b>"
    )
    
    kb = addin.product_card_kb(product_id, stock)
    
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    except Exception:
        await call.message.edit_text(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data.startswith("buy:"))
async def process_buy(call: CallbackQuery):
    product_id = int(call.data.split(":")[1])
    user_id = call.from_user.id
    
    result = await db.buy_product(user_id, product_id)
    
    if result["success"]:
        key = result["key"]
        balance = result["balance"]
        
        text = (
            f"✅ <b>Успешная покупка!</b>\n"
            f"━━━━━━━━━━━━━\n"
            f"Ваш ключ:\n\n"
            f"<code>{key}</code>\n\n"
            f"💰 Остаток на балансе: <b>{balance} ₽</b>"
        )
        await call.message.answer(text)
        await call.answer("Ключ выдан!")
        
        await addin.notify_admin_purchase(call.bot, user_id, product_id, key)
    else:
        await call.answer(result["error"], show_alert=True)

@router.callback_query(F.data == "profile:deposit")
async def show_deposit(call: CallbackQuery):
    text = (
        "💰 <b>Пополнение баланса</b>\n"
        "━━━━━━━━━━━━━\n\n"
        "Выберите удобный способ оплаты:"
    )
    kb = addin.deposit_kb()
    
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    except Exception:
        await call.message.edit_text(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "deposit:crypto")
async def deposit_crypto(call: CallbackQuery):
    url = await addin.create_crypto_invoice(call.from_user.id, 500)
    if url:
        text = "💳 Счет создан! Оплатите по кнопке ниже."
        kb = addin.crypto_pay_kb(url)
        await call.message.edit_caption(caption=text, reply_markup=kb)
    else:
        await call.answer("Ошибка создания счета", show_alert=True)

@router.callback_query(F.data == "deposit:admin")
async def deposit_admin(call: CallbackQuery):
    text = (
        "👨‍💻 <b>Пополнение через админа</b>\n"
        "━━━━━━━━━━━━━\n\n"
        "Напишите администратору для пополнения баланса вручную."
    )
    kb = addin.admin_pay_kb()
    try:
        await call.message.edit_caption(caption=text, reply_markup=kb)
    except Exception:
        await call.message.edit_text(text=text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "menu:back")
async def back_to_main(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    balance = user['balance'] if user else 0

    settings = await db.get_screen_settings("start")
    text = settings.get("text", "Привет!")
    
    text = text.replace("{name}", call.from_user.first_name or "друг")
    text = text.replace("{balance}", str(balance))
    
    photo = settings.get("photo_id")
    kb = addin.main_menu_kb(settings)
    
    try:
        if photo:
            await call.message.edit_media(media=addin.InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
        else:
            await call.message.edit_text(text=text, reply_markup=kb)
    except Exception:
        if photo:
            await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else:
            await call.message.answer(text=text, reply_markup=kb)
    await call.answer()

async def main():
    logging.basicConfig(level=logging.INFO)
    await db.init_db()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(admin.router)
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped")
