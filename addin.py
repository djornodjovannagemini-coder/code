import asyncio
import logging
import os
from typing import List, Dict, Any

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Для интеграции с CryptoBot (нужно будет установить: pip install aiocryptopay)
try:
    from aiocryptopay import AioCryptoPay, Networks
except ImportError:
    AioCryptoPay = None

# Получаем токены из .env
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
SUPPORT_LINK = "https://t.me/cxepy" # Ссылка на поддержку (можно вынести в БД)

# Инициализация клиента CryptoBot (если токен указан)
crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN, network=Networks.MAIN_NET) if CRYPTO_PAY_TOKEN and AioCryptoPay else None


# ================= КЛАВИАТУРЫ ГЛАВНОГО МЕНЮ =================

def main_menu_kb(settings: dict = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    # 1 ряд: Профиль (синяя) | Магазин (синяя)
    builder.button(
        text="Профиль", callback_data="menu:profile", style="primary",
        icon_custom_emoji_id="6032693626394382504"
    )
    builder.button(
        text="Магазин", callback_data="menu:shop", style="primary",
        icon_custom_emoji_id="5348475279960456198"
    )
    # 2 ряд: Информация (зеленая) | Канал (зеленая)
    builder.button(
        text="Информация", callback_data="menu:info", style="success",
        icon_custom_emoji_id="5348507247402040764"
    )
    builder.button(
        text="Канал", url="https://t.me/anthropc_claude", style="success",
        icon_custom_emoji_id="5260268501515377807"
    )
    # 3 ряд: Поддержка (красная)
    builder.button(
        text="Поддержка", url=SUPPORT_LINK, style="danger",
        icon_custom_emoji_id="5258513401784573443"
    )
    
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def profile_kb(settings: dict = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="Пополнить баланс", callback_data="profile:deposit", style="success",
        icon_custom_emoji_id="5429098361636560179"
    )
    builder.button(
        text="Покупки", callback_data="profile:purchases", style="primary",
        icon_custom_emoji_id="5429412504134525920"
    )
    builder.button(
        text="Промокод", callback_data="profile:promo", style="primary",
        icon_custom_emoji_id="5427375590124598857"
    )
    builder.button(
        text="Рефералка", callback_data="profile:referral", style="primary",
        icon_custom_emoji_id="5429256253224299845"
    )
    builder.button(
        text="Назад", callback_data="menu:back", style="danger",
        icon_custom_emoji_id="5888484185261216745"
    )
    
    builder.adjust(1, 2, 2)
    return builder.as_markup()


def shop_menu_kb(settings: dict = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="API-ключи", callback_data="shop:api", style="success",
        icon_custom_emoji_id="5427112068111184025"
    )
    builder.button(
        text="Назад", callback_data="menu:back", style="danger",
        icon_custom_emoji_id="5888484185261216745"
    )
    
    builder.adjust(1, 1)
    return builder.as_markup()


# ================= КЛАВИАТУРЫ МАГАЗИНА =================

def products_list_kb(products: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    for product in products:
        # Для каждого товара создаем кнопку. ID эмодзи можно тоже вынести в БД, но пока хардкод
        builder.button(
            text=product['name'], 
            callback_data=f"shop:product:{product['id']}", 
            style="primary",
            icon_custom_emoji_id="5427112068111184025" 
        )
    
    builder.button(
        text="Назад", callback_data="menu:shop", style="danger",
        icon_custom_emoji_id="5888484185261216745"
    )
    
    builder.adjust(1) # Каждый товар на новой строке
    return builder.as_markup()


def product_card_kb(product_id: int, stock: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    if stock > 0:
        builder.button(
            text="Купить", callback_data=f"buy:{product_id}", style="success",
            icon_custom_emoji_id="5429098361636560179" # Используем эмодзи "Пополнить" как заглушку для покупки
        )
    else:
        builder.button(
            text="Нет в наличии", callback_data="noop", style="danger"
        )
        
    builder.button(
        text="Назад", callback_data="shop:api", style="danger",
        icon_custom_emoji_id="5888484185261216745"
    )
    
    builder.adjust(1, 1)
    return builder.as_markup()


# ================= КЛАВИАТУРЫ ОПЛАТЫ =================

def deposit_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="CryptoBot (USDT)", callback_data="deposit:crypto", style="primary"
    )
    builder.button(
        text="Через админа", callback_data="deposit:admin", style="primary"
    )
    builder.button(
        text="Назад", callback_data="menu:profile", style="danger",
        icon_custom_emoji_id="5888484185261216745"
    )
    
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def crypto_pay_kb(url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Оплатить в CryptoBot", url=url, style="success")
    builder.button(text="Назад", callback_data="profile:deposit", style="danger")
    builder.adjust(1, 1)
    return builder.as_markup()


def admin_pay_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Написать админу", url=SUPPORT_LINK, style="primary")
    builder.button(text="Назад", callback_data="profile:deposit", style="danger")
    builder.adjust(1, 1)
    return builder.as_markup()


# ================= ИНТЕГРАЦИИ И УВЕДОМЛЕНИЯ =================

async def create_crypto_invoice(user_id: int, amount_rub: int) -> str | None:
    """Создает счет в CryptoBot. Возвращает ссылку на оплату."""
    if not crypto:
        logging.warning("CryptoBot token not set or aiocryptopay not installed.")
        return None
        
    try:
        # Примерный курс: 1 USDT = 90 RUB (в реале нужно брать с API)
        amount_usdt = round(amount_rub / 90.0, 2)
        
        invoice = await crypto.create_invoice(
            asset="USDT",
            amount=amount_usdt,
            description=f"Пополнение баланса на {amount_rub} ₽",
            payload=f"deposit:{user_id}"
        )
        return invoice.bot_invoice_url
    except Exception as e:
        logging.error(f"CryptoBot Error: {e}")
        return None


async def notify_admin_purchase(bot: Bot, user_id: int, product_id: int, key: str):
    """Уведомляет админов о новой покупке."""
    text = (
        f"💰 <b>Новая покупка!</b>\n"
        f"━━━━━━━━━━━━━\n"
        f"👤 Юзер: <code>{user_id}</code>\n"
        f"📦 Товар ID: {product_id}\n"
        f"🔑 Ключ: <code>{key}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def broadcast_stock_update(bot: Bot, users: List[int], product_id: int, product_name: str, added_qty: int, total_qty: int, price: int):
    """
    Рассылка при пополнении товара.
    Тот самый шаблон, который ты просил.
    """
    text = (
        f"📦 <b>Пополнение товара!</b>\n"
        f"<b>━━━━━━━━━━━━━</b>\n"
        f" {product_name}\n"
        f"• Добавлено: {added_qty} шт.\n"
        f"• Доступно сейчас: {total_qty} шт.\n"
        f"• Цена: {price} ₽"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(
        text="Перейти к товару",
        callback_data=f"shop:product:{product_id}",
        style="success",
        icon_custom_emoji_id="5427112068111184025" # Эмодзи ключа
    )
    kb = builder.as_markup()
    
    success_count = 0
    for uid in users:
        try:
            await bot.send_message(uid, text=text, reply_markup=kb)
            success_count += 1
            await asyncio.sleep(0.05) # Защита от лимитов Telegram
        except Exception:
            pass # Юзер заблокировал бота
            
    logging.info(f"Stock broadcast sent to {success_count} users.")
