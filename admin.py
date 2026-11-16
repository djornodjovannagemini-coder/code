import asyncio
import html
import logging
import os

from dotenv import load_dotenv

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import addin
import database as db
import payments

logger = logging.getLogger(__name__)

# .env читается до ADMIN_IDS, иначе админы не определяются
load_dotenv()

raw_ids = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in raw_ids.split(",") if x.strip().isdigit()]
logger.info("🔑 Загруженные ID админов: %s", ADMIN_IDS)

router = Router()
# Все callback-и админки закрыты фильтром: чужие нажатия уходят в клиентский роутер
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

SCREENS = {"start": "Старт", "profile": "Профиль", "shop": "Магазин",
           "deposit": "Пополнение", "info": "Информация",
           "purchases": "Покупки", "promo": "Промокод", "ref": "Рефералка",
           "terms": "Пользовательское соглашение", "privacy": "Политика конфиденциальности",
           "agreement": "Экран согласия"}


def is_adm(uid):
    return uid in ADMIN_IDS


def _emo(emoji_id: str, char: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{char}</tg-emoji>'


def _money(amount) -> str:
    return f"{int(amount):,}".replace(",", " ")


async def announce_product(bot: Bot, product_id: int, added: int, report_to: int) -> None:
    """Рассылает анонс пополнения всем активным юзерам и отчитывается админу."""
    product = await db.get_product(product_id)
    if not product or not product['is_active'] or added <= 0:
        return
    stock = await db.get_product_stock(product_id)
    text = (
        f"{_emo(addin.STOCK_EMOJI, '📦')} <b>Пополнение товара!</b>\n"
        f"<b>━━━━━━━━━━━━━</b>\n"
        f"{_emo(addin.PRODUCT_EMOJI, '🛍')} <b>{html.escape(product['name'])}</b>\n"
        f"• Добавлено: <b>{added} шт.</b>\n"
        f"• Доступно сейчас: <b>{stock} шт.</b>\n"
        f"• Цена: <b>{_money(product['price'])} ₽</b>"
    )
    kb = await addin.product_link_kb(product_id)
    users = await db.get_all_users_ids()
    sent, failed = 0, 0
    for uid in users:
        try:
            await bot.send_message(uid, text, reply_markup=kb)
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug("Анонс товара %s: не доставлено %s (%s)", product_id, uid, e)
        await asyncio.sleep(0.05)
    try:
        await bot.send_message(report_to, f"Анонс «{html.escape(product['name'])}»: доставлено {sent}, ошибок {failed}")
    except Exception:
        logger.warning("Не удалось отправить отчёт об анонсе админу %s", report_to)


def _utf16_to_idx(text: str, units: int) -> int:
    """Переводит UTF-16 смещение из Telegram в индекс Python-строки.

    Telegram считает offset/length в UTF-16, а эмодзи там занимает 2 единицы,
    поэтому обычная нарезка text[offset:offset+length] съезжает на любом эмодзи.
    """
    if units <= 0:
        return 0
    seen = 0
    for i, ch in enumerate(text):
        if seen >= units:
            return i
        seen += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def apply_custom_emoji(text: str, entities) -> str:
    """Оборачивает кастомные эмодзи в <tg-emoji ...>, сохраняя абсолютно все.

    Замены идут справа налево, чтобы смещения оставались валидными,
    и по индексам, а не через replace() — повторяющиеся эмодзи не путаются.
    """
    if not text or not entities:
        return text

    spans = []
    for e in entities:
        if e.type != "custom_emoji" or not getattr(e, "custom_emoji_id", None):
            continue
        start = _utf16_to_idx(text, e.offset)
        end = _utf16_to_idx(text, e.offset + e.length)
        if end > start:
            spans.append((start, end, e.custom_emoji_id))

    for start, end, emoji_id in sorted(spans, key=lambda s: s[0], reverse=True):
        chunk = text[start:end]
        text = f'{text[:start]}<tg-emoji emoji-id="{emoji_id}">{chunk}</tg-emoji>{text[end:]}'
    return text


class Adm(StatesGroup):
    # Товары
    p_name = State(); p_desc = State(); p_price = State(); p_type = State(); p_items = State()
    p_stock_items = State()
    # Юзеры
    u_id = State(); u_amount = State(); u_ban_id = State()
    # Оформление
    d_text = State(); d_photo = State()
    # Рассылка
    b_msg = State()
    # Промокоды
    promo_code = State(); promo_discount = State(); promo_uses = State()
    # Настройки
    s_amounts = State(); s_ref = State()
    # Редактор кнопок
    btn_text = State(); btn_emoji = State(); btn_action = State(); btn_row = State()


# ================= ГЛАВНОЕ МЕНЮ =================
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_adm(message.from_user.id):
        return await message.answer(f"⛔ У вас нет доступа.\nВаш ID: <code>{message.from_user.id}</code>")
    await state.clear()
    await message.answer("🔧 <b>Админ-панель</b>", reply_markup=await addin.admin_main_kb())


@router.callback_query(F.data == "adm:menu")
async def adm_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    try:
        await call.message.edit_text("🔧 <b>Админ-панель</b>", reply_markup=await addin.admin_main_kb())
    except Exception:
        await call.message.answer("🔧 <b>Админ-панель</b>", reply_markup=await addin.admin_main_kb())


# ================= 1. ТОВАРЫ =================
@router.callback_query(F.data == "adm:prod")
async def adm_prod(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    products = await db.get_all_products()
    text = "📦 <b>Управление товарами</b>"
    if not products:
        text += "\n\nТоваров пока нет."
    else:
        text += f"\n\nВсего: <b>{len(products)}</b>"
        for p in products:
            stock = await db.get_product_stock(p['id'])
            mark = "🟢" if p['is_active'] else "🔴"
            text += f"\n{mark} #{p['id']} {html.escape(p['name'])} · {p['price']} ₽ · остаток {stock}"
    await call.message.edit_text(text, reply_markup=await addin.admin_products_kb())


@router.callback_query(F.data == "adm:prod:add")
async def add_p1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("1️⃣ Введите название товара:", reply_markup=await addin.admin_back_kb())
    await state.set_state(Adm.p_name)


@router.message(Adm.p_name)
async def add_p2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    await state.update_data(name=msg.text)
    await msg.answer("2️⃣ Введите описание:")
    await state.set_state(Adm.p_desc)


@router.message(Adm.p_desc)
async def add_p3(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    await state.update_data(desc=msg.text)
    await msg.answer("3️⃣ Введите цену (число):")
    await state.set_state(Adm.p_price)


@router.message(Adm.p_price)
async def add_p4(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if not msg.text.isdigit():
        return await msg.answer("❌ Только число!")
    await state.update_data(price=int(msg.text))
    kb = InlineKeyboardBuilder()
    kb.button(text="Текст/Ключ", callback_data="p_type_text", style="primary")
    kb.button(text="Ссылка", callback_data="p_type_link", style="primary")
    kb.button(text="Файл", callback_data="p_type_file", style="primary")
    kb.adjust(3)
    await msg.answer("4️⃣ Выберите тип товара:", reply_markup=kb.as_markup())
    await state.set_state(Adm.p_type)


@router.callback_query(Adm.p_type)
async def add_p5(call: CallbackQuery, state: FSMContext):
    if not is_adm(call.from_user.id):
        return await state.clear()
    if not call.data.startswith("p_type_"):
        await state.clear()
        return await adm_menu(call, state)
    await call.answer()
    p_type = call.data.replace("p_type_", "")
    await state.update_data(type=p_type)
    await call.message.edit_text("5️⃣ Отправьте содержимое (текст/ключи по одному в строке, ссылку или файл):")
    await state.set_state(Adm.p_items)


@router.message(Adm.p_items)
async def add_p6(msg: Message, state: FSMContext, bot: Bot):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    data = await state.get_data()
    if msg.document:
        items = [msg.document.file_id]
    elif msg.text:
        items = [x.strip() for x in msg.text.split("\n") if x.strip()]
    else:
        return await msg.answer("❌ Неверный формат.")

    pid = await db.add_product(data['name'], data['desc'], data['price'], data['type'])
    count = await db.add_product_items(pid, items)
    await state.clear()
    await msg.answer(f"Товар <b>{html.escape(data['name'])}</b> добавлен! ({count} шт.)",
                     reply_markup=await addin.admin_main_kb())
    asyncio.create_task(announce_product(bot, pid, count, msg.chat.id))


@router.callback_query(F.data == "adm:prod:toggle")
async def prod_toggle_list(call: CallbackQuery):
    await call.answer()
    products = await db.get_all_products()
    if not products:
        return await call.answer("Товаров нет", show_alert=True)
    await call.message.edit_text("Выберите товар, чтобы скрыть/показать:",
                                 reply_markup=await addin.admin_product_pick_kb(products, "toggle"))


@router.callback_query(F.data.startswith("adm:prod:toggle:"))
async def prod_toggle(call: CallbackQuery):
    await call.answer("Готово")
    pid = int(call.data.split(":")[3])
    product = await db.get_product(pid)
    if not product:
        return await call.message.edit_text("Товар не найден", reply_markup=await addin.admin_back_kb())
    await db.toggle_product(pid, 0 if product['is_active'] else 1)
    products = await db.get_all_products()
    await call.message.edit_text("Выберите товар, чтобы скрыть/показать:",
                                 reply_markup=await addin.admin_product_pick_kb(products, "toggle"))


@router.callback_query(F.data == "adm:prod:del")
async def prod_del_list(call: CallbackQuery):
    await call.answer()
    products = await db.get_all_products()
    if not products:
        return await call.answer("Товаров нет", show_alert=True)
    await call.message.edit_text("Выберите товар для удаления (вместе с остатками):",
                                 reply_markup=await addin.admin_product_pick_kb(products, "del"))


@router.callback_query(F.data.startswith("adm:prod:del:"))
async def prod_del(call: CallbackQuery):
    pid = int(call.data.split(":")[3])
    await db.delete_product(pid)
    await call.answer("Удалено")
    products = await db.get_all_products()
    await call.message.edit_text("Выберите товар для удаления (вместе с остатками):",
                                 reply_markup=await addin.admin_product_pick_kb(products, "del"))


@router.callback_query(F.data == "adm:prod:stock")
async def prod_stock_list(call: CallbackQuery):
    await call.answer()
    products = await db.get_all_products()
    if not products:
        return await call.answer("Товаров нет", show_alert=True)
    await call.message.edit_text("Выберите товар, чтобы добавить позиции:",
                                 reply_markup=await addin.admin_product_pick_kb(products, "stock"))


@router.callback_query(F.data.startswith("adm:prod:stock:"))
async def prod_stock_pick(call: CallbackQuery, state: FSMContext):
    await call.answer()
    pid = int(call.data.split(":")[3])
    product = await db.get_product(pid)
    if not product:
        return await call.message.edit_text("Товар не найден", reply_markup=await addin.admin_back_kb())
    await state.update_data(product_id=pid)
    await state.set_state(Adm.p_stock_items)
    await call.message.edit_text(
        f"Отправьте новые позиции для <b>{html.escape(product['name'])}</b>:\n"
        "текст/ключи по одному в строке или файл."
    )


@router.message(Adm.p_stock_items)
async def prod_stock_add(msg: Message, state: FSMContext, bot: Bot):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    data = await state.get_data()
    if msg.document:
        items = [msg.document.file_id]
    elif msg.text:
        items = [x.strip() for x in msg.text.split("\n") if x.strip()]
    else:
        return await msg.answer("❌ Неверный формат.")
    count = await db.add_product_items(data['product_id'], items)
    stock = await db.get_product_stock(data['product_id'])
    await state.clear()
    await msg.answer(f"Добавлено {count} шт. Всего в наличии: {stock}.",
                     reply_markup=await addin.admin_main_kb())
    asyncio.create_task(announce_product(bot, data['product_id'], count, msg.chat.id))


# ================= 2. ЮЗЕРЫ =================
@router.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    total = await db.count_users()
    await call.message.edit_text(f"👥 <b>Пользователи</b>\n\nВсего: <b>{total}</b>",
                                 reply_markup=await addin.admin_users_kb())


@router.callback_query(F.data == "adm:users:list")
async def users_list(call: CallbackQuery):
    await call.answer()
    users = await db.get_users(limit=10)
    if not users:
        return await call.message.edit_text("Юзеров нет", reply_markup=await addin.admin_users_kb())
    text = "👥 <b>Последние пользователи</b>\n<b>━━━━━━━━━━━━━</b>"
    for u in users:
        mark = "⛔️" if u['is_banned'] else "•"
        text += (f"\n{mark} <a href=\"tg://user?id={u['user_id']}\">{html.escape(u['first_name'] or '—')}</a> "
                 f"· <code>{u['user_id']}</code> · {u['balance']} ₽")
    await call.message.edit_text(text, reply_markup=await addin.admin_users_kb())


@router.callback_query(F.data == "adm:users:bal")
async def u_bal1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Введите Telegram ID пользователя:", reply_markup=await addin.admin_back_kb())
    await state.set_state(Adm.u_id)


@router.message(Adm.u_id)
async def u_bal2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if not msg.text.isdigit():
        return await msg.answer("❌ ID - это число.")
    user = await db.get_user(int(msg.text))
    if not user:
        return await msg.answer("❌ Не найден.")
    await state.update_data(uid=int(msg.text))
    await msg.answer(f"Юзер: {html.escape(user['first_name'] or '—')}\nБаланс: {user['balance']} ₽\n\n"
                     "Введите сумму (+500 или -100):")
    await state.set_state(Adm.u_amount)


@router.message(Adm.u_amount)
async def u_bal3(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    raw = (msg.text or "").strip()
    if not raw.lstrip("+-").isdigit():
        return await msg.answer("❌ Только число.")
    amount = int(raw)
    data = await state.get_data()
    await db.add_balance(data['uid'], amount)
    user = await db.get_user(data['uid'])
    await msg.answer(f"✅ Баланс изменён на {amount:+d} ₽.\nТеперь: {user['balance']} ₽.",
                     reply_markup=await addin.admin_main_kb())
    await state.clear()


@router.callback_query(F.data == "adm:users:ban")
async def u_ban1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Введите Telegram ID пользователя:", reply_markup=await addin.admin_back_kb())
    await state.set_state(Adm.u_ban_id)


@router.message(Adm.u_ban_id)
async def u_ban2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if not msg.text.isdigit():
        return await msg.answer("❌ ID - это число.")
    user = await db.get_user(int(msg.text))
    if not user:
        return await msg.answer("❌ Не найден.")
    await state.clear()
    status = "забанен" if user['is_banned'] else "активен"
    await msg.answer(
        f"{html.escape(user['first_name'] or '—')} · <code>{user['user_id']}</code>\nСтатус: {status}",
        reply_markup=await addin.admin_user_ban_kb(user),
    )


@router.callback_query(F.data.startswith("adm:users:ban:"))
async def u_ban_do(call: CallbackQuery):
    uid = int(call.data.split(":")[3])
    await db.set_ban(uid, 1)
    await call.answer("Забанен")
    user = await db.get_user(uid)
    await call.message.edit_text(
        f"{html.escape(user['first_name'] or '—')} · <code>{uid}</code>\nСтатус: забанен",
        reply_markup=await addin.admin_user_ban_kb(user),
    )


@router.callback_query(F.data.startswith("adm:users:unban:"))
async def u_unban_do(call: CallbackQuery):
    uid = int(call.data.split(":")[3])
    await db.set_ban(uid, 0)
    await call.answer("Разбанен")
    user = await db.get_user(uid)
    await call.message.edit_text(
        f"{html.escape(user['first_name'] or '—')} · <code>{uid}</code>\nСтатус: активен",
        reply_markup=await addin.admin_user_ban_kb(user),
    )


# ================= 3. ЗАКАЗЫ =================
@router.callback_query(F.data == "adm:orders")
async def adm_orders(call: CallbackQuery):
    await call.answer()
    orders = await db.get_recent_orders(limit=15)
    if not orders:
        return await call.message.edit_text("🧾 <b>Заказы</b>\n\nЗаказов пока нет.",
                                            reply_markup=await addin.admin_back_kb())
    text = "🧾 <b>Последние заказы</b>\n<b>━━━━━━━━━━━━━</b>"
    for o in orders:
        when = o['order_date'].strftime("%d.%m %H:%M") if o['order_date'] else "—"
        text += (f"\n#{o['id']} · {html.escape(o['name'] or '—')} · {o['price']} ₽\n"
                 f"   <code>{o['user_id']}</code> · {when}")
    await call.message.edit_text(text, reply_markup=await addin.admin_back_kb())


# ================= 4. ПРОМОКОДЫ =================
@router.callback_query(F.data == "adm:promos")
async def adm_promos(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    promos = await db.list_promos()
    text = "🎟 <b>Промокоды</b>"
    if not promos:
        text += "\n\nПромокодов нет."
    else:
        text += "\n\nНажмите на промокод, чтобы удалить."
    await call.message.edit_text(text, reply_markup=await addin.admin_promos_kb(promos))


@router.callback_query(F.data == "adm:promos:add")
async def promo_add1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Введите текст промокода (например WELCOME10):",
                                 reply_markup=await addin.admin_back_kb())
    await state.set_state(Adm.promo_code)


@router.message(Adm.promo_code)
async def promo_add2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    code = (msg.text or "").strip()
    if not code or " " in code:
        return await msg.answer("❌ Промокод без пробелов.")
    await state.update_data(code=code)
    await msg.answer("Введите размер скидки в процентах (1-90):")
    await state.set_state(Adm.promo_discount)


@router.message(Adm.promo_discount)
async def promo_add3(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if not msg.text.isdigit() or not (1 <= int(msg.text) <= 90):
        return await msg.answer("❌ Число от 1 до 90.")
    await state.update_data(discount=int(msg.text))
    await msg.answer("Сколько раз можно использовать промокод?")
    await state.set_state(Adm.promo_uses)


@router.message(Adm.promo_uses)
async def promo_add4(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if not msg.text.isdigit() or int(msg.text) < 1:
        return await msg.answer("❌ Число больше нуля.")
    data = await state.get_data()
    await db.create_promo(data['code'], data['discount'], int(msg.text))
    await state.clear()
    promos = await db.list_promos()
    await msg.answer(f"✅ Промокод <code>{html.escape(data['code'])}</code> создан.",
                     reply_markup=await addin.admin_promos_kb(promos))


@router.callback_query(F.data.startswith("adm:promos:del:"))
async def promo_del(call: CallbackQuery):
    code = call.data.split(":", 3)[3]
    await db.delete_promo(code)
    await call.answer("Удалён")
    promos = await db.list_promos()
    text = "🎟 <b>Промокоды</b>" + ("\n\nПромокодов нет." if not promos else "\n\nНажмите на промокод, чтобы удалить.")
    await call.message.edit_text(text, reply_markup=await addin.admin_promos_kb(promos))


# ================= 5. РАССЫЛКА =================
@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("📢 Отправьте сообщение для рассылки (текст или фото):",
                                 reply_markup=await addin.admin_back_kb())
    await state.set_state(Adm.b_msg)


@router.message(Adm.b_msg)
async def do_broadcast(msg: Message, state: FSMContext, bot: Bot):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    await state.clear()
    users = await db.get_all_users_ids()
    await msg.answer(f"⏳ Начинаю рассылку на {len(users)} юзеров...")
    sent, failed = 0, 0
    for uid in users:
        try:
            if msg.photo:
                await bot.send_photo(uid, msg.photo[-1].file_id, caption=msg.caption)
            else:
                await bot.send_message(uid, msg.text)
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug("Рассылка: не доставлено %s (%s)", uid, e)
        await asyncio.sleep(0.05)
    await msg.answer(f"✅ Доставлено: {sent}/{len(users)} (ошибок: {failed})",
                     reply_markup=await addin.admin_main_kb())


# ================= 6. ОФОРМЛЕНИЕ =================
@router.callback_query(F.data == "adm:design")
async def adm_design(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await call.message.edit_text("🎨 <b>Оформление</b>\n\nВыберите экран:",
                                 reply_markup=await addin.admin_design_kb())


@router.callback_query(F.data.startswith("adm:design:"))
async def design_screen(call: CallbackQuery):
    await call.answer()
    screen = call.data.split(":")[2]
    if screen not in SCREENS:
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Текст экрана", callback_data=f"adm:ed:t:{screen}", style="primary")
    kb.button(text="🖼 Картинка", callback_data=f"adm:ed:p:{screen}", style="primary")
    kb.button(text="Назад", callback_data="adm:design", style="danger")
    kb.adjust(1, 1, 1)
    await call.message.edit_text(f"Настройка экрана <b>{SCREENS[screen]}</b>:", reply_markup=kb.as_markup())


@router.callback_query(F.data.startswith("adm:ed:t:"))
async def edit_text_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen)
    await call.message.edit_text(
        f"Отправьте новый текст для <b>{SCREENS.get(screen, screen)}</b>.\n"
        "Кастомные эмодзи сохраняются как есть.\n"
        "Отправьте <code>-</code>, чтобы оставить без изменений."
    )
    await state.set_state(Adm.d_text)


@router.message(Adm.d_text)
async def process_new_text(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    data = await state.get_data()
    screen = data['screen']

    if msg.text == "-":
        await msg.answer("Текст оставлен без изменений.")
    else:
        if msg.text is not None:
            new_text, entities = msg.text, msg.entities or []
        elif msg.caption is not None:
            new_text, entities = msg.caption, msg.caption_entities or []
        else:
            return await msg.answer("❌ Отправьте текст или фото с подписью.")

        new_text = apply_custom_emoji(new_text, entities)
        if len(new_text) > 4000:
            return await msg.answer("❌ Слишком длинный текст: лимит 4000 символов.")
        await db.set_setting(f"{screen}_text", new_text)
        await msg.answer(f"✅ Текст экрана «{SCREENS.get(screen, screen)}» обновлён!")

    kb = InlineKeyboardBuilder()
    kb.button(text="Назад", callback_data="adm:design", style="danger")
    await msg.answer("Вернуться в оформление?", reply_markup=kb.as_markup())
    await state.clear()


@router.callback_query(F.data.startswith("adm:ed:p:"))
async def edit_photo_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen)
    await call.message.edit_text(
        f"Отправьте новое фото для <b>{SCREENS.get(screen, screen)}</b> (или <code>0</code> для удаления):"
    )
    await state.set_state(Adm.d_photo)


@router.message(Adm.d_photo)
async def process_new_photo(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    data = await state.get_data()
    screen = data['screen']

    if msg.text == "0":
        await db.set_setting(f"{screen}_photo", "")
        await msg.answer("Фото удалено.")
    elif msg.photo:
        await db.set_setting(f"{screen}_photo", msg.photo[-1].file_id)
        await msg.answer("✅ Фото обновлено!")
    else:
        return await msg.answer("❌ Отправьте фото или 0.")

    kb = InlineKeyboardBuilder()
    kb.button(text="Назад", callback_data="adm:design", style="danger")
    await msg.answer("Вернуться в оформление?", reply_markup=kb.as_markup())
    await state.clear()


# ================= 7. НАСТРОЙКИ =================
async def settings_text():
    tech = await db.get_setting("tech_work", "0")
    amounts = await db.get_setting("deposit_amounts", "")
    ref = await db.get_setting("ref_percent", "5")
    min_d = await db.get_setting("min_deposit", "50")
    max_d = await db.get_setting("max_deposit", "10000")
    pay = "✅ CryptoBot подключён" if payments.enabled() else "⚠️ токен не задан, оплата вручную"
    agree = "ВКЛ" if await db.get_setting("require_agreement", "1") == "1" else "ВЫКЛ"
    return (f"⚙️ <b>Настройки</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            f"🛠 Тех. работы: <b>{'ВКЛ' if tech == '1' else 'ВЫКЛ'}</b>\n"
            f"💰 Суммы пополнения: <b>{amounts}</b>\n"
            f"📉 Лимиты: <b>{min_d}–{max_d} ₽</b>\n"
            f"🔗 Реф. процент: <b>{ref}%</b>\n"
            f"💳 Оплата: {pay}\n"
            f"📄 Согласие при старте: <b>{agree}</b>")


@router.callback_query(F.data == "adm:settings")
async def adm_settings(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    tech = await db.get_setting("tech_work", "0")
    await call.message.edit_text(await settings_text(),
                                 reply_markup=await addin.admin_settings_kb(tech, payments.enabled(), await db.get_setting("require_agreement", "1")))


@router.callback_query(F.data == "adm:settings:tech")
async def toggle_tech(call: CallbackQuery):
    tech = await db.get_setting("tech_work", "0")
    new_tech = "1" if tech == "0" else "0"
    await db.set_setting("tech_work", new_tech)
    await call.answer("Тех. работы " + ("включены" if new_tech == "1" else "выключены"))
    await call.message.edit_text(await settings_text(),
                                 reply_markup=await addin.admin_settings_kb(new_tech, payments.enabled(), await db.get_setting("require_agreement", "1")))


@router.callback_query(F.data == "adm:settings:agree")
async def toggle_agreement(call: CallbackQuery):
    current = await db.get_setting("require_agreement", "1")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("require_agreement", new_value)
    await call.answer("Согласие " + ("включено" if new_value == "1" else "выключено"))
    tech = await db.get_setting("tech_work", "0")
    await call.message.edit_text(await settings_text(),
                                 reply_markup=await addin.admin_settings_kb(tech, payments.enabled(), await db.get_setting("require_agreement", "1")))


@router.callback_query(F.data == "adm:settings:amounts")
async def set_amounts1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text(
        "Отправьте суммы кнопок пополнения через запятую.\n"
        "Например: <code>100,250,500,1000</code>\n"
        "Отправьте <code>-</code> для отмены."
    )
    await state.set_state(Adm.s_amounts)


@router.message(Adm.s_amounts)
async def set_amounts2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if msg.text == "-":
        await state.clear()
        return await msg.answer("Отменено.", reply_markup=await addin.admin_main_kb())
    parts = [p.strip() for p in (msg.text or "").replace(" ", "").split(",") if p.strip()]
    if not parts or not all(p.isdigit() for p in parts):
        return await msg.answer("❌ Только числа через запятую.")
    await db.set_setting("deposit_amounts", ",".join(parts))
    await state.clear()
    await msg.answer(f"✅ Суммы обновлены: {', '.join(parts)}", reply_markup=await addin.admin_main_kb())


@router.callback_query(F.data == "adm:settings:ref")
async def set_ref1(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("Отправьте реферальный процент (0-50). Отправьте <code>-</code> для отмены.")
    await state.set_state(Adm.s_ref)


@router.message(Adm.s_ref)
async def set_ref2(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    if msg.text == "-":
        await state.clear()
        return await msg.answer("Отменено.", reply_markup=await addin.admin_main_kb())
    if not msg.text.isdigit() or not (0 <= int(msg.text) <= 50):
        return await msg.answer("❌ Число от 0 до 50.")
    await db.set_setting("ref_percent", msg.text)
    await state.clear()
    await msg.answer(f"✅ Реф. процент: {msg.text}%", reply_markup=await addin.admin_main_kb())


# ================= 8. СТАТИСТИКА =================
@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    await call.answer()
    s = await db.get_stats()
    products = await db.get_all_products()
    text = (f"📊 <b>Статистика</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            f"👥 Юзеров: <b>{s['users']}</b>\n"
            f"🧾 Заказов: <b>{s['orders']}</b>\n"
            f"💰 Продаж: <b>{s['sales']} ₽</b>\n"
            f"💳 Пополнений: <b>{s['topped']} ₽</b>\n"
            f"⏳ Необработанных заявок: <b>{s['pending']}</b>\n"
            f"📦 Товаров: <b>{len(products)}</b>")
    await call.message.edit_text(text, reply_markup=await addin.admin_back_kb())


# ================= 9. ФИНАНСЫ =================
@router.callback_query(F.data == "adm:finance")
async def adm_finance(call: CallbackQuery):
    await call.answer()
    await render_finance(call)


async def render_finance(call: CallbackQuery):
    pending = await db.get_deposits("pending", limit=10)
    paid = await db.get_deposits("paid", limit=10)
    text = "💳 <b>Финансы</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
    if pending:
        text += "<b>Ожидают подтверждения:</b>\n"
        for d in pending:
            text += f"#{d['id']} · {d['amount']} ₽ · <code>{d['user_id']}</code> · {d['method']}\n"
    else:
        text += "Заявок на пополнение нет.\n"
    if paid:
        text += "\n<b>Последние пополнения:</b>\n"
        for d in paid:
            when = d['paid_at'].strftime("%d.%m %H:%M") if d['paid_at'] else "—"
            text += f"#{d['id']} · {d['amount']} ₽ · {when}\n"
    await call.message.edit_text(text, reply_markup=await addin.admin_pending_deposits_kb(pending))


@router.callback_query(F.data.startswith("adm:dep:ok:"))
async def dep_ok(call: CallbackQuery, bot: Bot):
    dep_id = int(call.data.split(":")[3])
    if not await bot_credit(bot, dep_id):
        return await call.answer("Заявка уже обработана", show_alert=True)
    await call.answer("Зачислено")
    await render_finance(call)


@router.callback_query(F.data.startswith("adm:dep:no:"))
async def dep_no(call: CallbackQuery):
    dep_id = int(call.data.split(":")[3])
    await db.cancel_deposit(dep_id)
    await call.answer("Отклонено")
    await render_finance(call)


async def bot_credit(bot: Bot, dep_id: int) -> bool:
    """Ручное подтверждение заявки: тот же путь, что и автооплата."""
    dep = await db.get_deposit(dep_id)
    if not dep or dep['status'] != 'pending':
        return False
    percent = int(await db.get_setting("ref_percent", "5") or 0)
    result = await db.mark_deposit_paid(dep_id, percent)
    if not result:
        return False
    try:
        await bot.send_message(
            dep['user_id'],
            f"✅ Баланс пополнен на <b>{dep['amount']} ₽</b>\nТекущий баланс: <b>{result['balance']} ₽</b>",
            reply_markup=await addin.simple_kb("to_profile"),
        )
    except Exception:
        logger.warning("Не удалось уведомить юзера %s о пополнении", dep['user_id'])
    if result['ref']:
        try:
            await bot.send_message(result['ref']['user_id'],
                                   f"🔗 Реферальное начисление: <b>{result['ref']['amount']} ₽</b>")
        except Exception:
            pass
    return True


# ================= 10. СИСТЕМА =================
@router.callback_query(F.data == "adm:system")
async def adm_system(call: CallbackQuery):
    await call.answer()
    products = await db.get_all_products()
    stock = sum([await db.get_product_stock(p['id']) for p in products]) if products else 0
    text = (f"🛡 <b>Система</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            f"👤 Админы: <code>{', '.join(map(str, ADMIN_IDS)) or '—'}</code>\n"
            f"📦 Товаров: <b>{len(products)}</b> · позиций в наличии: <b>{stock}</b>\n"
            f"💳 Оплата: {'CryptoBot' if payments.enabled() else 'вручную (нет токена)'}\n"
            f"🛠 Тех. работы: <b>{'ВКЛ' if await db.get_setting('tech_work', '0') == '1' else 'ВЫКЛ'}</b>\n"
            f"📄 Приняли условия: <b>{await db.count_accepted()}</b>")
    await call.message.edit_text(text, reply_markup=await addin.admin_back_kb())


# ================= 11. РЕДАКТОР КНОПОК =================
BUTTON_SCREENS = [
    ("main", "Главное меню"),
    ("profile", "Профиль"),
    ("shop", "Магазин"),
    ("deposit", "Пополнение баланса"),
    ("product", "Карточка товара"),
    ("product_back", "Карточка: нет в наличии"),
    ("purchases", "Мои покупки"),
    ("promo", "Промокод"),
    ("promo_active", "Активный промокод"),
    ("info", "Информация"),
    ("ref", "Рефералка"),
    ("cancel", "Отмена ввода суммы"),
    ("to_deposit", "Кнопка «Пополнить»"),
    ("to_profile", "Кнопка «Назад в профиль»"),
    ("back_shop", "Кнопка «Назад в магазин»"),
    ("agreement", "Экран согласия"),
    ("terms", "Пользовательское соглашение"),
    ("privacy", "Политика конфиденциальности"),
    ("choose_payment", "Выбор способа оплаты"),
    ("crypto_pay", "Оплата криптой"),
    ("crypto_expired", "Счёт истёк"),
    ("announce", "Анонс пополнения товара"),
    ("adm_main", "Админка: главное"),
    ("adm_back", "Админка: «Назад»"),
    ("adm_products", "Админка: товары"),
    ("adm_product_pick", "Админка: выбор товара"),
    ("adm_users", "Админка: юзеры"),
    ("adm_user_ban", "Админка: бан"),
    ("adm_design", "Админка: оформление"),
    ("adm_settings", "Админка: настройки"),
    ("adm_promos", "Админка: промокоды"),
    ("adm_finance", "Админка: финансы"),
]
SCREEN_PAGE = 10
BTN_PAGE = 8
STYLE_NAMES = {"primary": "синий", "success": "зелёный", "danger": "красный"}
STYLE_ORDER = ["primary", "success", "danger"]


def split_custom_emoji(text: str, entities):
    """Достаёт id первого кастомного эмодзи и возвращает текст без него."""
    if not text:
        return "", None
    spans = []
    for e in entities or []:
        if e.type == "custom_emoji" and getattr(e, "custom_emoji_id", None):
            start = _utf16_to_idx(text, e.offset)
            end = _utf16_to_idx(text, e.offset + e.length)
            if end > start:
                spans.append((start, end, e.custom_emoji_id))
    emoji_id = spans[0][2] if spans else None
    for start, end, _ in sorted(spans, key=lambda s: s[0], reverse=True):
        text = text[:start] + text[end:]
    return text.strip(), emoji_id


def _nav_row(builder, page: int, pages: int, prefix: str):
    if pages <= 1:
        return
    left = addin.btn("◀", f"{prefix}{page - 1}", style="primary") if page > 0 else addin.btn("·", "adm:btn:noop", style="primary")
    right = addin.btn("▶", f"{prefix}{page + 1}", style="primary") if page < pages - 1 else addin.btn("·", "adm:btn:noop", style="primary")
    builder.row(left, addin.btn(f"{page + 1}/{pages}", "adm:btn:noop", style="primary"), right)


async def render_btn_screens(call, page: int = 0):
    pages = max(1, (len(BUTTON_SCREENS) + SCREEN_PAGE - 1) // SCREEN_PAGE)
    page = min(max(page, 0), pages - 1)
    builder = InlineKeyboardBuilder()
    for key, title in BUTTON_SCREENS[page * SCREEN_PAGE:(page + 1) * SCREEN_PAGE]:
        builder.row(addin.btn(title, f"adm:btn:s:{key}", style="primary"))
    _nav_row(builder, page, pages, "adm:btn:p:")
    builder.row(addin.btn("Назад", "adm:design", style="danger", emoji=addin.BACK_EMOJI))
    text = ("🔘 <b>Кнопки</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            "Выберите экран. Дальше можно менять текст, цвет, эмодзи, действие и ряд кнопки.")
    await call.message.edit_text(text, reply_markup=builder.as_markup())


async def render_screen_buttons(call, screen: str, page: int = 0):
    buttons = await db.get_buttons(screen, only_active=False)
    pages = max(1, (len(buttons) + BTN_PAGE - 1) // BTN_PAGE)
    page = min(max(page, 0), pages - 1)
    builder = InlineKeyboardBuilder()
    for b in buttons[page * BTN_PAGE:(page + 1) * BTN_PAGE]:
        mark = "" if b['is_active'] else "🚫 "
        builder.row(addin.btn(f"{mark}{b['text']}", f"adm:btn:e:{b['button_key']}",
                              style=b['style'] or "primary", emoji=b['emoji_id'] or None))
    _nav_row(builder, page, pages, f"adm:btn:pg:{screen}:")
    builder.row(addin.btn("К экранам", "adm:btn", style="danger", emoji=addin.BACK_EMOJI))
    title = dict(BUTTON_SCREENS).get(screen, screen)
    text = (f"🔘 <b>{html.escape(title)}</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            f"Кнопок: <b>{len(buttons)}</b>\n"
            "Кнопки показаны так, как их видят пользователи. Нажмите, чтобы изменить.")
    await call.message.edit_text(text, reply_markup=builder.as_markup())


async def render_button_edit(call, key: str):
    b = await db.get_button(key)
    if not b:
        return await deny(call, "Кнопка не найдена")
    if b['callback_data']:
        action = f"callback: {b['callback_data']}"
    elif b['url']:
        action = f"URL: {b['url']}"
    else:
        action = "нет (кнопка не отправится)"
    text = (f"🔘 <b>{html.escape(b['text'])}</b>\n<b>━━━━━━━━━━━━━</b>\n\n"
            f"Экран: <code>{b['screen']}</code>\n"
            f"Цвет: <b>{STYLE_NAMES.get(b['style'], b['style'])}</b>\n"
            f"Эмодзи: <code>{b['emoji_id'] or '—'}</code>\n"
            f"Действие: <code>{html.escape(action)}</code>\n"
            f"Ряд: <b>{b['row_num']}</b> · Позиция: <b>{b['position']}</b>\n"
            f"Статус: <b>{'показана' if b['is_active'] else 'скрыта'}</b>")
    builder = InlineKeyboardBuilder()
    builder.row(addin.btn("Текст", f"adm:btn:t:{key}", style="primary"))
    builder.row(addin.btn("Цвет", f"adm:btn:c:{key}", style="primary"))
    builder.row(addin.btn("Эмодзи", f"adm:btn:i:{key}", style="primary"))
    builder.row(addin.btn("Действие", f"adm:btn:a:{key}", style="primary"))
    builder.row(addin.btn("Скрыть" if b['is_active'] else "Показать", f"adm:btn:v:{key}", style="primary"))
    builder.row(addin.btn("Ряд", f"adm:btn:r:{key}", style="primary"))
    builder.row(addin.btn("К списку", f"adm:btn:s:{b['screen']}", style="danger", emoji=addin.BACK_EMOJI))
    await call.message.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "adm:btn")
async def btn_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await render_btn_screens(call, 0)


@router.callback_query(F.data.startswith("adm:btn:p:"))
async def btn_menu_page(call: CallbackQuery):
    await call.answer()
    await render_btn_screens(call, int(call.data.split(":")[3]))


@router.callback_query(F.data == "adm:btn:noop")
async def btn_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data.startswith("adm:btn:pg:"))
async def btn_screen_page(call: CallbackQuery):
    await call.answer()
    _, _, _, screen, page = call.data.split(":")
    await render_screen_buttons(call, screen, int(page))


@router.callback_query(F.data.startswith("adm:btn:s:"))
async def btn_screen(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await render_screen_buttons(call, call.data.split(":", 3)[3])


@router.callback_query(F.data.startswith("adm:btn:e:"))
async def btn_edit(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await render_button_edit(call, call.data.split(":", 3)[3])


@router.callback_query(F.data.startswith("adm:btn:c:"))
async def btn_color(call: CallbackQuery):
    key = call.data.split(":", 3)[3]
    b = await db.get_button(key)
    if not b:
        return await call.answer("Кнопка не найдена", show_alert=True)
    current = b['style'] if b['style'] in STYLE_ORDER else "primary"
    new_style = STYLE_ORDER[(STYLE_ORDER.index(current) + 1) % len(STYLE_ORDER)]
    await db.update_button(key, style=new_style)
    await call.answer(f"Цвет: {STYLE_NAMES[new_style]}")
    await render_button_edit(call, key)


@router.callback_query(F.data.startswith("adm:btn:v:"))
async def btn_visible(call: CallbackQuery):
    key = call.data.split(":", 3)[3]
    b = await db.get_button(key)
    if not b:
        return await call.answer("Кнопка не найдена", show_alert=True)
    await db.update_button(key, is_active=0 if b['is_active'] else 1)
    await call.answer("Скрыта" if b['is_active'] else "Показана")
    await render_button_edit(call, key)


async def _btn_field_start(call, state, key, target_state, prompt):
    b = await db.get_button(key)
    if not b:
        return await call.answer("Кнопка не найдена", show_alert=True)
    await call.answer()
    await state.set_state(target_state)
    await state.update_data(key=key)
    builder = InlineKeyboardBuilder()
    builder.row(addin.btn("Отмена", f"adm:btn:e:{key}", style="danger", emoji=addin.BACK_EMOJI))
    await call.message.edit_text(prompt, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("adm:btn:t:"))
async def btn_text_start(call: CallbackQuery, state: FSMContext):
    await _btn_field_start(
        call, state, call.data.split(":", 3)[3], Adm.btn_text,
        "Отправьте новый текст кнопки (до 64 символов).\n"
        "Можно вставить кастомный эмодзи — бот сам возьмёт его ID и поставит перед текстом.\n"
        "Отправьте <code>-</code> для отмены.")


@router.callback_query(F.data.startswith("adm:btn:i:"))
async def btn_emoji_start(call: CallbackQuery, state: FSMContext):
    await _btn_field_start(
        call, state, call.data.split(":", 3)[3], Adm.btn_emoji,
        "Отправьте один кастомный эмодзи — он встанет перед текстом кнопки.\n"
        "Отправьте <code>0</code>, чтобы убрать эмодзи, или <code>-</code> для отмены.")


@router.callback_query(F.data.startswith("adm:btn:a:"))
async def btn_action_start(call: CallbackQuery, state: FSMContext):
    await _btn_field_start(
        call, state, call.data.split(":", 3)[3], Adm.btn_action,
        "Отправьте callback-данные (например <code>menu:shop</code>) или ссылку <code>https://…</code>.\n"
        "Отправьте <code>0</code>, чтобы убрать действие, или <code>-</code> для отмены.")


@router.callback_query(F.data.startswith("adm:btn:r:"))
async def btn_row_start(call: CallbackQuery, state: FSMContext):
    await _btn_field_start(
        call, state, call.data.split(":", 3)[3], Adm.btn_row,
        "Отправьте номер ряда (1–9), в котором должна стоять кнопка.\n"
        "Отправьте <code>-</code> для отмены.")


def _btn_back_kb(key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(addin.btn("К кнопке", f"adm:btn:e:{key}", style="primary"))
    return builder.as_markup()


@router.message(Adm.btn_text)
async def btn_text_set(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    key = (await state.get_data()).get('key')
    if msg.text == "-":
        await state.clear()
        return await msg.answer("Отменено.")
    text, emoji_id = split_custom_emoji(msg.text or "", msg.entities or [])
    if not text:
        return await msg.answer("Текст не может быть пустым.")
    if len(text) > 64:
        return await msg.answer("Слишком длинный текст: Telegram разрешает до 64 символов.")
    if emoji_id:
        await db.update_button(key, text=text, emoji_id=emoji_id)
    else:
        await db.update_button(key, text=text)
    await state.clear()
    await msg.answer(f"Текст обновлён: <b>{html.escape(text)}</b>"
                     + (f"\nЭмодзи: <code>{emoji_id}</code>" if emoji_id else ""),
                     reply_markup=_btn_back_kb(key))


@router.message(Adm.btn_emoji)
async def btn_emoji_set(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    key = (await state.get_data()).get('key')
    raw = (msg.text or "").strip()
    if raw == "-":
        await state.clear()
        return await msg.answer("Отменено.")
    if raw == "0":
        await db.update_button(key, emoji_id=None)
        await state.clear()
        return await msg.answer("Эмодзи убран.", reply_markup=_btn_back_kb(key))
    _, emoji_id = split_custom_emoji(msg.text or "", msg.entities or [])
    if not emoji_id:
        return await msg.answer("Не нашёл кастомный эмодзи. Отправьте кастомный эмодзи, <code>0</code> или <code>-</code>.")
    await db.update_button(key, emoji_id=emoji_id)
    await state.clear()
    await msg.answer(f"Эмодзи обновлён: <code>{emoji_id}</code>", reply_markup=_btn_back_kb(key))


@router.message(Adm.btn_action)
async def btn_action_set(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    key = (await state.get_data()).get('key')
    raw = (msg.text or "").strip()
    if raw == "-":
        await state.clear()
        return await msg.answer("Отменено.")
    if raw == "0":
        await db.update_button(key, callback_data=None)
        await db.update_button(key, url=None)
        await state.clear()
        return await msg.answer("Действие убрано: кнопка не будет отображаться.", reply_markup=_btn_back_kb(key))
    if raw.startswith("http://") or raw.startswith("https://"):
        await db.update_button(key, url=raw)
        await db.update_button(key, callback_data=None)
        await state.clear()
        return await msg.answer(f"Ссылка обновлена: <code>{html.escape(raw)}</code>", reply_markup=_btn_back_kb(key))
    if " " in raw or len(raw.encode()) > 64:
        return await msg.answer("Callback без пробелов и не длиннее 64 байт.")
    await db.update_button(key, callback_data=raw)
    await db.update_button(key, url=None)
    await state.clear()
    await msg.answer(f"Callback обновлён: <code>{html.escape(raw)}</code>", reply_markup=_btn_back_kb(key))


@router.message(Adm.btn_row)
async def btn_row_set(msg: Message, state: FSMContext):
    if not is_adm(msg.from_user.id):
        return await state.clear()
    key = (await state.get_data()).get('key')
    raw = (msg.text or "").strip()
    if raw == "-":
        await state.clear()
        return await msg.answer("Отменено.")
    if not raw.isdigit() or not (1 <= int(raw) <= 9):
        return await msg.answer("Нужен номер ряда от 1 до 9.")
    await db.update_button(key, row_num=int(raw))
    await state.clear()
    await msg.answer(f"Кнопка перенесена в ряд {int(raw)}.", reply_markup=_btn_back_kb(key))
