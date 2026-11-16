import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from dotenv import load_dotenv
import admin, addin, database as db

load_dotenv()

# Настраиваем логирование ДО всего остального
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    if await db.get_setting("tech_work") == "1" and message.from_user.id not in ADMIN_IDS:
        return await message.answer("🛠 Бот на технических работах. Зайдите позже.")
    await db.register_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    user = await db.get_user(message.from_user.id)
    text = await db.get_setting("start_text")
    text = text.replace("{name}", message.from_user.first_name or "друг").replace("{balance}", str(user['balance']))
    photo = await db.get_setting("start_photo")
    kb = await addin.main_menu_kb()
    if photo:
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)

@router.callback_query(F.data == "menu:profile")
async def show_profile(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    if not user: return await call.answer("Напишите /start", show_alert=True)
    text = await db.get_setting("profile_text")
    text = text.replace("{name}", user['first_name']).replace("{balance}", str(user['balance']))
    text = text.replace("{spent}", str(user['total_spent'])).replace("{purchases}", str(user['purchases_count'])).replace("{user_id}", str(user['user_id']))
    photo = await db.get_setting("profile_photo")
    kb = await addin.profile_kb()
    try:
        if photo: await call.message.edit_media(media=addin.InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
        else: await call.message.edit_text(text, reply_markup=kb)
    except:
        if photo: await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else: await call.message.answer(text, reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "menu:shop")
async def show_shop(call: CallbackQuery):
    kb = await addin.shop_menu_kb()
    try: await call.message.edit_text("🛍 <b>Магазин</b>\nВыберите раздел:", reply_markup=kb)
    except: await call.message.answer("🛍 <b>Магазин</b>", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data == "menu:back")
async def back_to_main(call: CallbackQuery):
    user = await db.get_user(call.from_user.id)
    text = await db.get_setting("start_text")
    text = text.replace("{name}", call.from_user.first_name or "друг").replace("{balance}", str(user['balance'] if user else 0))
    photo = await db.get_setting("start_photo")
    kb = await addin.main_menu_kb()
    try:
        if photo: await call.message.edit_media(media=addin.InputMediaPhoto(media=photo, caption=text), reply_markup=kb)
        else: await call.message.edit_text(text, reply_markup=kb)
    except:
        if photo: await call.message.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else: await call.message.answer(text, reply_markup=kb)
    await call.answer()

async def main():
    logger.info("=== 1. Starting bot initialization ===")
    
    if not BOT_TOKEN:
        logger.critical("❌ BOT_TOKEN не задан в переменных окружения!")
        raise ValueError("BOT_TOKEN missing")
    
    logger.info("=== 2. Connecting to PostgreSQL ===")
    try:
        await db.init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.critical(f"❌ DATABASE INIT FAILED: {e}", exc_info=True)
        raise
    
    logger.info("=== 3. Creating bot instance ===")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    logger.info(f"✅ Bot authenticated: @{me.username} (id={me.id})")
    
    dp = Dispatcher()
    dp.include_router(admin.router)
    dp.include_router(router)
    logger.info("✅ Routers included")
    
    logger.info("=== 4. Deleting webhook & starting polling ===")
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Уведомляем админов, что бот успешно запустился
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "✅ Бот успешно запущен и подключен к БД!")
        except Exception as e:
            logger.warning(f"Не смог отправить уведомление админу {admin_id}: {e}")
    
    logger.info("✅ Bot is up and running! Start polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"🔥 FATAL ERROR: {e}", exc_info=True)
        raise  # Важно: пробрасываем ошибку, чтобы Railway её увидел
