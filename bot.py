import asyncio
import html
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv

# .env читается ДО импорта database/admin, иначе DATABASE_URL и ADMIN_IDS берутся из пустого окружения.
load_dotenv()

from aiogram import BaseMiddleware, Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InputMediaPhoto, Message

import admin
import addin
import database as db
import payments

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

BOT_USERNAME = ""
POLL_INTERVAL = 5

router = Router()


class User(StatesGroup):
    amount = State()
    promo = State()


def emo(emoji_id: str, char: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>'


def money(amount) -> str:
    if isinstance(amount, float) and amount != int(amount):
        whole, frac = f"{amount:,.2f}".split(".")
        return f"{whole.replace(',', ' ')},{frac}"
    return f"{int(amount):,}".replace(",", " ")


async def fill(key: str, **values) -> str:
    text = await db.get_setting(key)
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


async def show(call: CallbackQuery, text: str, kb, photo: str = "") -> None:
    """Правит текущее сообщение: подменяет фото/текст или пересоздаёт его, если Telegram не даёт изменить."""
    msg = call.message
    try:
        if photo:
            await msg.edit_media(
                media=InputMediaPhoto(media=photo, caption=text, parse_mode=ParseMode.HTML),
                reply_markup=kb,
            )
        elif msg.photo or msg.video or msg.document or msg.animation:
            await msg.edit_caption(caption=text, reply_markup=kb)
        else:
            await msg.edit_text(text, reply_markup=kb)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        logger.warning("Не удалось изменить сообщение (%s), отправляю новое", e)
        try:
            await msg.delete()
        except TelegramBadRequest:
            pass
        if photo:
            await msg.answer_photo(photo=photo, caption=text, reply_markup=kb)
        else:
            await msg.answer(text, reply_markup=kb)


async def deny(call: CallbackQuery, text: str) -> None:
    await call.answer(text, show_alert=True)


async def deposit_presets():
    raw = await db.get_setting("deposit_amounts", "100,250,500,1000,2500,5000,10000")
    return [int(x) for x in raw.replace(" ", "").split(",") if x.isdigit()]


class AccessMiddleware(BaseMiddleware):
    """Отсекает забаненных и держит технические работы, не пуская их в хендлеры."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user and user.id not in ADMIN_IDS:
            is_call = isinstance(event, CallbackQuery)
            if await db.get_setting("tech_work", "0") == "1":
                text = "Бот на технических работах. Зайдите позже."
                if is_call:
                    await event.answer(text, show_alert=True)
                else:
                    await event.answer(text)
                return
            db_user = await db.get_user(user.id)
            if db_user and db_user['is_banned']:
                if is_call:
                    await event.answer("Доступ ограничен.", show_alert=True)
                else:
                    await event.answer("Доступ ограничен.")
                return
        return await handler(event, data)


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user = message.from_user
    ref = None
    if command.args and command.args.isdigit():
        ref_id = int(command.args)
        if ref_id != user.id:
            ref = ref_id

    await db.register_user(user.id, user.first_name, user.username, ref)
    await show_start(message)


async def show_start(message: Message):
    user = await db.get_user(message.from_user.id)
    text = await fill("start_text", name=html.escape(message.from_user.first_name or "друг"),
                      balance=user['balance'] if user else 0)
    kb = await addin.main_menu_kb()
    photo = await db.get_setting("start_photo")
    if photo:
        await message.answer_photo(photo=photo, caption=text, reply_markup=kb)
    else:
        await message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "menu:back")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    user = await db.get_user(call.from_user.id)
    text = await fill("start_text", name=html.escape(call.from_user.first_name or "друг"),
                      balance=user['balance'] if user else 0)
    await show(call, text, await addin.main_menu_kb(), await db.get_setting("start_photo"))


@router.callback_query(F.data == "menu:profile")
async def show_profile(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    user = await db.get_user(call.from_user.id)
    if not user:
        return await deny(call, "Напишите /start")
    text = await fill(
        "profile_text",
        name=html.escape(user['first_name'] or "друг"), balance=user['balance'],
        spent=user['total_spent'], purchases=user['purchases_count'],
        refs=await db.count_refs(user['user_id']), ref_earned=user['ref_earned'] or 0,
        user_id=user['user_id'],
    )
    await show(call, text, await addin.profile_kb(), await db.get_setting("profile_photo"))


@router.callback_query(F.data == "menu:info")
async def show_info(call: CallbackQuery):
    await call.answer()
    await show(call, await db.get_setting("info_text"), await addin.simple_kb("info"),
               await db.get_setting("info_photo"))


@router.callback_query(F.data == "menu:shop")
async def show_shop(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    products = await db.get_active_products()
    text = await db.get_setting("shop_text")
    if not products:
        text += "\n\nПока пусто — товары скоро появятся."
    await show(call, text, await addin.shop_menu_kb(products), await db.get_setting("shop_photo"))


@router.callback_query(F.data.startswith("shop:item:"))
async def show_product(call: CallbackQuery):
    await call.answer()
    product_id = int(call.data.split(":")[2])
    product = await db.get_product(product_id)
    if not product or not product['is_active']:
        return await deny(call, "Товар недоступен")
    stock = await db.get_product_stock(product_id)
    promo = await db.get_user_promo(call.from_user.id)
    price = int(product['price'] * (100 - promo['discount']) / 100) if promo else product['price']
    text = (
        f"<b>{html.escape(product['name'])}</b>\n"
        f"<b>━━━━━━━━━━━━━</b>\n\n"
        f"{html.escape(product['description'] or '')}\n\n"
        f"{emo(addin.MONEY_EMOJI, '💵')} Цена: <b>{price} ₽</b>"
        + (f" <i>(скидка {promo['discount']}%)</i>" if promo else "") + "\n"
        f"{emo(addin.PURCHASES_EMOJI, '🛒')} В наличии: <b>{stock}</b>"
    )
    await show(call, text, await addin.product_kb(product_id, stock > 0))


async def deliver(bot: Bot, user_id: int, product: dict, content: str) -> bool:
    name = html.escape(product['name'])
    try:
        if product['item_type'] == 'file':
            await bot.send_document(user_id, content, caption=f"<b>{name}</b>")
        elif product['item_type'] == 'link':
            await bot.send_message(user_id, f"<b>{name}</b>\n\n{html.escape(content)}")
        else:
            await bot.send_message(user_id, f"<b>{name}</b>\n\n<code>{html.escape(content)}</code>")
        return True
    except Exception:
        logger.exception("Не удалось выдать товар %s юзеру %s", product['id'], user_id)
        return False


async def notify_admins(bot: Bot, text: str) -> None:
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logger.warning("Не удалось отправить уведомление админу %s", admin_id)


@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery, bot: Bot):
    product_id = int(call.data.split(":")[1])
    product = await db.get_product(product_id)
    if not product or not product['is_active']:
        return await deny(call, "Товар недоступен")

    promo = await db.get_user_promo(call.from_user.id)
    discount = promo['discount'] if promo else 0
    result = await db.buy_product(call.from_user.id, product_id, discount)
    if not result['success']:
        if result['error'] != "Недостаточно средств":
            return await deny(call, result['error'])
        user = await db.get_user(call.from_user.id)
        need = result['price'] - (user['balance'] if user else 0)
        await call.answer("Недостаточно средств", show_alert=True)
        return await call.message.answer(
            f"Не хватает <b>{money(need)} ₽</b> — пополните баланс.",
            reply_markup=await addin.simple_kb("to_deposit"),
        )

    if promo:
        await db.consume_promo(call.from_user.id)
    await call.answer("Оплачено")
    delivered = await deliver(bot, call.from_user.id, product, result['content'])
    await notify_admins(
        bot,
        f"🛒 Покупка: {html.escape(product['name'])} · {result['price']} ₽\n"
        f"Юзер: <code>{call.from_user.id}</code>"
        + ("" if delivered else f"\n⚠️ Выдача упала, проверьте товар #{product_id}"),
    )
    await show(
        call,
        f"{emo(addin.PURCHASES_EMOJI, '🛒')} <b>{html.escape(product['name'])}</b> — куплено\n<b>━━━━━━━━━━━━━</b>\n\n"
        f"Товар отправлен сообщением выше.\n"
        f"{emo(addin.BALANCE_EMOJI, '💰')} Баланс: <b>{result['balance']} ₽</b>",
        await addin.simple_kb("back_shop"),
    )


@router.callback_query(F.data == "profile:purchases")
async def show_purchases(call: CallbackQuery):
    await call.answer()
    orders = await db.get_user_orders(call.from_user.id, limit=20)
    text = await db.get_setting("purchases_text")
    if not orders:
        text += "\n\nПокупок пока нет."
    else:
        for order in orders:
            when = order['order_date'].strftime("%d.%m.%Y %H:%M") if order['order_date'] else "—"
            block = f"\n\n<b>{html.escape(order['name'] or 'Товар')}</b> · {order['price']} ₽\n<i>{when}</i>"
            if order['content']:
                block += f"\n<code>{html.escape(order['content'])}</code>"
            if len(text) + len(block) > 3800:
                text += "\n\n<i>…показаны не все покупки</i>"
                break
            text += block
    await show(call, text, await addin.simple_kb("purchases"), await db.get_setting("purchases_photo"))


@router.callback_query(F.data == "profile:deposit")
async def show_deposit(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await show(call, await db.get_setting("deposit_text"),
               await addin.deposit_kb(await deposit_presets()), await db.get_setting("deposit_photo"))


@router.callback_query(F.data == "dep:custom")
async def custom_amount(call: CallbackQuery, state: FSMContext):
    await call.answer()
    min_d = await db.get_setting("min_deposit", "50")
    max_d = await db.get_setting("max_deposit", "10000")
    await state.set_state(User.amount)
    await show(call, f"Напишите сумму в рублях цифрами, например 500 — от {money(min_d)}₽ до {money(max_d)}₽.",
               await addin.cancel_kb())


@router.message(User.amount)
async def process_amount(msg: Message, state: FSMContext, bot: Bot):
    raw = (msg.text or "").strip().replace(" ", "")
    if not raw.isdigit():
        return await msg.answer("Только целое число, например 500.", reply_markup=await addin.cancel_kb())
    await state.clear()
    await start_payment(bot, msg, msg.from_user.id, int(raw))


@router.callback_query(F.data.startswith("dep:amount:"))
async def preset_amount(call: CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    await call.answer()
    await start_payment(bot, call.message, call.from_user.id, int(call.data.split(":")[2]))


async def start_payment(bot: Bot, message: Message, user_id: int, amount: int):
    min_d = int(await db.get_setting("min_deposit", "50") or 50)
    max_d = int(await db.get_setting("max_deposit", "10000") or 10000)
    if amount < min_d or amount > max_d:
        text = f"Сумма должна быть от {money(min_d)}₽ до {money(max_d)}₽."
        return await message.answer(text, reply_markup=await addin.cancel_kb())

    dep_id = await db.create_deposit(user_id, amount, "choose")
    await notify_admins(bot, f"💳 Заявка #{dep_id}: пополнение {amount} ₽\nЮзер: <code>{user_id}</code>")
    text = await fill("choose_text", amount=money(amount), order_id=dep_id)
    support = await db.get_setting("support_url", "https://t.me/cxepy")
    await message.answer(text, reply_markup=await addin.choose_payment_kb(dep_id, support))


@router.callback_query(F.data.startswith("dep:pay:"))
async def pay_crypto(call: CallbackQuery, bot: Bot):
    dep_id = int(call.data.split(":")[2])
    dep = await db.get_deposit(dep_id)
    if not dep or dep['user_id'] != call.from_user.id:
        return await deny(call, "Заказ не найден")
    if dep['status'] == 'paid':
        return await deny(call, "Заказ уже оплачен")
    if not payments.enabled():
        return await deny(call, "Оплата криптой временно недоступна, выберите оплату через админа.")

    fee_percent = float(await db.get_setting("crypto_fee", "3") or 0)
    minutes = int(await db.get_setting("crypto_ttl_minutes", "5") or 5)
    amount = dep['amount']
    fee_amount = round(amount * fee_percent / 100, 2)
    total = round(amount + fee_amount, 2)

    invoice = await payments.create_invoice(total, f"dep:{dep_id}", expires_in=minutes * 60)
    if not invoice:
        return await deny(call, "Не удалось создать счёт, попробуйте позже")

    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=minutes)
    await db.set_deposit_invoice(dep_id, invoice['id'], expires_at, "crypto")

    usd = f"{invoice['usdt']:.2f}" if invoice.get('usdt') else "—"
    text = await fill(
        "crypto_text", amount=money(amount), fee=f"{fee_percent:g}",
        fee_amount=money(fee_amount), total=money(total), usd=usd, minutes=minutes,
    )
    await call.answer()
    await show(call, text, await addin.crypto_pay_kb(invoice['url'], dep_id))
    asyncio.create_task(
        watch_deposit(bot, dep_id, invoice['id'], minutes, call.message.chat.id, call.message.message_id)
    )


@router.callback_query(F.data.startswith("dep:back:"))
async def back_to_choose(call: CallbackQuery):
    dep_id = int(call.data.split(":")[2])
    dep = await db.get_deposit(dep_id)
    if not dep or dep['user_id'] != call.from_user.id or dep['status'] == 'paid':
        return await deny(call, "Заказ не найден")
    await call.answer()
    text = await fill("choose_text", amount=money(dep['amount']), order_id=dep_id)
    support = await db.get_setting("support_url", "https://t.me/cxepy")
    await show(call, text, await addin.choose_payment_kb(dep_id, support))


async def credit_deposit(bot: Bot, dep_id: int) -> bool:
    dep = await db.get_deposit(dep_id)
    if not dep:
        return False
    percent = int(await db.get_setting("ref_percent", "5") or 0)
    result = await db.mark_deposit_paid(dep_id, percent)
    if not result:
        return False
    try:
        await bot.send_message(
            dep['user_id'],
            f"{emo(addin.BALANCE_EMOJI, '💰')} Баланс пополнен на <b>{dep['amount']} ₽</b>\n"
            f"Текущий баланс: <b>{result['balance']} ₽</b>",
            reply_markup=await addin.simple_kb("to_profile"),
        )
    except Exception:
        logger.warning("Не удалось уведомить юзера %s о пополнении", dep['user_id'])
    await notify_admins(bot, f"💰 Пополнение #{dep_id}: {dep['amount']} ₽\nЮзер: <code>{dep['user_id']}</code>")
    if result['ref']:
        try:
            await bot.send_message(
                result['ref']['user_id'],
                f"{emo(addin.REF_EMOJI, '🔗')} Реферальное начисление: <b>{result['ref']['amount']} ₽</b>",
            )
        except Exception:
            logger.warning("Не удалось уведомить реферера %s", result['ref']['user_id'])
    return True


async def watch_deposit(bot: Bot, dep_id: int, invoice_id: str, minutes: int, chat_id: int, message_id: int):
    for _ in range(max(1, minutes * 60 // POLL_INTERVAL)):
        await asyncio.sleep(POLL_INTERVAL)
        try:
            if await payments.is_paid(invoice_id):
                await credit_deposit(bot, dep_id)
                return
        except Exception:
            logger.exception("Ошибка фоновой проверки депозита %s", dep_id)

    dep = await db.get_deposit(dep_id)
    if not dep or dep['status'] != 'pending':
        return
    await db.cancel_deposit(dep_id)
    await payments.delete_invoice(invoice_id)
    text = await db.get_setting("crypto_expired_text")
    try:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id,
                                    reply_markup=await addin.crypto_expired_kb(dep_id))
    except Exception:
        try:
            await bot.send_message(chat_id, text, reply_markup=await addin.crypto_expired_kb(dep_id))
        except Exception:
            logger.warning("Не удалось сообщить об истечении счёта %s", dep_id)


@router.callback_query(F.data.startswith("dep:check:"))
async def check_deposit(call: CallbackQuery, bot: Bot):
    dep_id = int(call.data.split(":")[2])
    dep = await db.get_deposit(dep_id)
    if not dep or dep['user_id'] != call.from_user.id:
        return await deny(call, "Счёт не найден")
    if dep['status'] == 'paid':
        return await deny(call, "Этот счёт уже зачислен")
    if not dep['invoice_id']:
        return await deny(call, "Оплата не найдена")

    if await payments.is_paid(dep['invoice_id']):
        await call.answer("Оплачено")
        await credit_deposit(bot, dep_id)
        user = await db.get_user(call.from_user.id)
        text = (f"{emo(addin.BALANCE_EMOJI, '💰')} Баланс пополнен на <b>{money(dep['amount'])} ₽</b>\n"
                f"Текущий баланс: <b>{money(user['balance'] if user else dep['amount'])} ₽</b>")
        return await show(call, text, await addin.simple_kb("to_profile"))

    expired = dep['status'] == 'canceled' or (
        dep.get('expires_at') and dep['expires_at'] < datetime.now(timezone.utc).replace(tzinfo=None)
    )
    if expired:
        await call.answer()
        text = await db.get_setting("crypto_expired_text")
        return await show(call, text, await addin.crypto_expired_kb(dep_id))

    await deny(call, "Оплата не найдена. Если вы только что заплатили — подождите минуту.")


@router.callback_query(F.data == "profile:promo")
async def show_promo(call: CallbackQuery, state: FSMContext):
    await call.answer()
    active = await db.get_user_promo(call.from_user.id)
    text = await db.get_setting("promo_text")
    if active:
        text += f"\n\n{emo(addin.PROMO_EMOJI, '🎟')} Активен: <b>{html.escape(active['code'])}</b> · скидка <b>{active['discount']}%</b>"
        return await show(call, text, await addin.promo_active_kb(), await db.get_setting("promo_photo"))
    await state.set_state(User.promo)
    await show(call, text + "\nНапример: <code>WELCOME10</code>", await addin.simple_kb("promo"),
               await db.get_setting("promo_photo"))


@router.message(User.promo)
async def apply_promo(msg: Message, state: FSMContext):
    code = (msg.text or "").strip()
    if not code:
        return await msg.answer("Отправьте промокод текстом.")
    promo = await db.get_promo(code)
    if not promo:
        return await msg.answer("Промокод не найден.", reply_markup=await addin.simple_kb("promo"))
    if promo['uses_left'] <= 0:
        return await msg.answer("Промокод больше не действует.", reply_markup=await addin.simple_kb("promo"))
    await db.set_user_promo(msg.from_user.id, promo['code'])
    await state.clear()
    await msg.answer(
        f"{emo(addin.PROMO_EMOJI, '🎟')} Промокод <code>{html.escape(promo['code'])}</code> активирован: "
        f"скидка <b>{promo['discount']}%</b> на следующую покупку.",
        reply_markup=await addin.simple_kb("to_profile"),
    )


@router.callback_query(F.data == "promo:reset")
async def reset_promo(call: CallbackQuery):
    await db.set_user_promo(call.from_user.id, None)
    await call.answer("Промокод отменён")
    await show(call, await db.get_setting("promo_text"), await addin.simple_kb("promo"),
               await db.get_setting("promo_photo"))


@router.callback_query(F.data == "profile:referral")
async def show_referral(call: CallbackQuery):
    await call.answer()
    user = await db.get_user(call.from_user.id)
    if not user:
        return await deny(call, "Напишите /start")
    link = f"https://t.me/{BOT_USERNAME}?start={call.from_user.id}"
    text = await fill(
        "ref_text",
        percent=await db.get_setting("ref_percent", "5"),
        refs=await db.count_refs(call.from_user.id),
        earned=user['ref_earned'] or 0,
        link=link,
    )
    await show(call, text, await addin.simple_kb("ref"), await db.get_setting("ref_photo"))


@router.callback_query()
async def unknown_callback(call: CallbackQuery):
    logger.warning("Нет хендлера для callback %s (юзер %s)", call.data, call.from_user.id)
    await call.answer("Кнопка неактуальна, откройте меню заново.", show_alert=True)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    global BOT_USERNAME

    await db.init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logger.info("Бот запущен как @%s", BOT_USERNAME)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(AccessMiddleware())
    dp.callback_query.outer_middleware(AccessMiddleware())
    dp.include_router(admin.router)
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await payments.close()
        await db.close_pool()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception:
        # раньше здесь стояло "except: pass" и бот молча умирал без логов
        logger.exception("Критическая ошибка, бот остановлен")
        sys.exit(1)
