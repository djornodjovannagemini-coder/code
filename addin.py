from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import database as db

# Набор кастомных эмодзи, используемых в интерфейсе
BACK_EMOJI = "5888484185261216745"
CUSTOM_AMOUNT_EMOJI = "5427016470729127056"
PURCHASES_EMOJI = "5429412504134525920"
PROMO_EMOJI = "5427375590124598857"
REF_EMOJI = "5429256253224299845"
SHOP_EMOJI = "5348475279960456198"
BALANCE_EMOJI = "5258204546391351475"
MONEY_EMOJI = "5769126056262898415"
DEPOSIT_EMOJI = "5429098361636560179"
CRYPTO_EMOJI = "5361836987642815474"
ADMIN_PAY_EMOJI = "5426948678965307932"
VERIFY_EMOJI = "5427398138702899667"
STOCK_EMOJI = "5429154960715588692"
PRODUCT_EMOJI = "5429250347644262814"


def btn(text: str, callback_data: str = None, url: str = None, style: str = "primary",
        emoji: str = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=callback_data,
        url=url,
        style=style,
        icon_custom_emoji_id=emoji,
    )


def back_btn(callback_data: str) -> InlineKeyboardButton:
    return btn("Назад", callback_data, style="danger", emoji=BACK_EMOJI)


async def build_keyboard_from_db(screen: str, back_screen: str = None) -> InlineKeyboardMarkup:
    buttons_data = await db.get_buttons(screen)
    kb = InlineKeyboardBuilder()

    rows = {}
    for b in buttons_data:
        rows.setdefault(b['row_num'], []).append(b)

    for r in sorted(rows.keys()):
        kb.row(*[btn(
            text=b['text'],
            callback_data=b['callback_data'] or None,
            url=b['url'] or None,
            style=b['style'] or "primary",
            emoji=b['emoji_id'] or None,
        ) for b in rows[r]])

    if back_screen:
        kb.row(back_btn(back_screen))

    return kb.as_markup()


async def main_menu_kb() -> InlineKeyboardMarkup:
    return await build_keyboard_from_db("main")


async def profile_kb() -> InlineKeyboardMarkup:
    return await build_keyboard_from_db("profile", back_screen="menu:back")


async def shop_menu_kb(products=None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in await db.get_buttons("shop"):
        kb.row(btn(
            text=b['text'],
            callback_data=b['callback_data'] or None,
            url=b['url'] or None,
            style=b['style'] or "primary",
            emoji=b['emoji_id'] or None,
        ))
    for p in products or []:
        kb.row(btn(f"{p['name']} · {p['price']} ₽", f"shop:item:{p['id']}", style="primary", emoji=SHOP_EMOJI))
    kb.row(back_btn("menu:back"))
    return kb.as_markup()


def deposit_kb(amounts) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for i in range(0, len(amounts), 2):
        kb.row(*[btn(f"{a} ₽", f"dep:amount:{a}", style="primary") for a in amounts[i:i + 2]])
    kb.row(btn("Своя сумма", "dep:custom", style="primary", emoji=CUSTOM_AMOUNT_EMOJI))
    kb.row(back_btn("menu:profile"))
    return kb.as_markup()


def cancel_kb(callback_data: str = "profile:deposit") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("Отмена", callback_data, style="danger", emoji=BACK_EMOJI))
    return kb.as_markup()


def choose_payment_kb(dep_id: int, support_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        btn("CryptoBot", callback_data=f"dep:pay:{dep_id}", style="primary", emoji=CRYPTO_EMOJI),
        btn("Через админа", url=support_url, style="primary", emoji=ADMIN_PAY_EMOJI),
    )
    return kb.as_markup()


def crypto_pay_kb(url: str, dep_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if url:
        kb.row(btn("Оплатить", url=url, style="success", emoji=DEPOSIT_EMOJI))
    kb.row(btn("Проверить оплату", f"dep:check:{dep_id}", style="primary", emoji=VERIFY_EMOJI))
    kb.row(back_btn(f"dep:back:{dep_id}"))
    return kb.as_markup()


def crypto_expired_kb(dep_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("Создать новый счёт", f"dep:pay:{dep_id}", style="success", emoji=DEPOSIT_EMOJI))
    kb.row(back_btn(f"dep:back:{dep_id}"))
    return kb.as_markup()


def product_kb(product_id: int, can_buy: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if can_buy:
        kb.row(btn("Купить", f"buy:{product_id}", style="success", emoji=MONEY_EMOJI))
    kb.row(back_btn("menu:shop"))
    return kb.as_markup()


def product_link_kb(product_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("Перейти к товару", f"shop:item:{product_id}", style="success", emoji=PURCHASES_EMOJI))
    return kb.as_markup()


def simple_kb(back_callback: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(back_btn(back_callback))
    return kb.as_markup()


def promo_active_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("Отменить промокод", "promo:reset", style="danger", emoji=BACK_EMOJI))
    kb.row(back_btn("profile:promo"))
    return kb.as_markup()


# ==================== АДМИНКА ====================
def admin_main_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📦 Товары", callback_data="adm:prod", style="primary")
    kb.button(text="👥 Юзеры", callback_data="adm:users", style="primary")
    kb.button(text="🧾 Заказы", callback_data="adm:orders", style="primary")
    kb.button(text="🎟 Промокоды", callback_data="adm:promos", style="primary")
    kb.button(text="📢 Рассылка", callback_data="adm:broadcast", style="primary")
    kb.button(text="🎨 Оформление", callback_data="adm:design", style="primary")
    kb.button(text="⚙️ Настройки", callback_data="adm:settings", style="primary")
    kb.button(text="📊 Статистика", callback_data="adm:stats", style="primary")
    kb.button(text="💳 Финансы", callback_data="adm:finance", style="primary")
    kb.button(text="🛡 Система", callback_data="adm:system", style="danger")
    kb.button(text="Выход", callback_data="menu:back", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(2, 2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    return kb.as_markup()


def admin_products_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="adm:prod:add", style="success")
    kb.button(text="📥 Пополнить остатки", callback_data="adm:prod:stock", style="success")
    kb.button(text="👁 Скрыть/Показать", callback_data="adm:prod:toggle", style="primary")
    kb.button(text="🗑 Удалить", callback_data="adm:prod:del", style="danger")
    kb.button(text="Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(1, 1, 1, 1, 1)
    return kb.as_markup()


def admin_product_pick_kb(products, action: str) -> InlineKeyboardMarkup:
    """action: toggle | del | stock"""
    kb = InlineKeyboardBuilder()
    for p in products:
        mark = "🟢" if p['is_active'] else "🔴"
        kb.row(btn(f"{mark} {p['name']} · {p['price']} ₽", f"adm:prod:{action}:{p['id']}", style="primary"))
    kb.row(admin_back_kb().inline_keyboard[0][0])
    return kb.as_markup()


def admin_users_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Изменить баланс", callback_data="adm:users:bal", style="success")
    kb.button(text="⛔️ Забанить / Разбанить", callback_data="adm:users:ban", style="danger")
    kb.button(text="📋 Список юзеров", callback_data="adm:users:list", style="primary")
    kb.button(text="Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def admin_user_ban_kb(user) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if user['is_banned']:
        kb.button(text="Разбанить", callback_data=f"adm:users:unban:{user['user_id']}", style="success")
    else:
        kb.button(text="Забанить", callback_data=f"adm:users:ban:{user['user_id']}", style="danger")
    kb.button(text="Назад", callback_data="adm:users", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(1, 1)
    return kb.as_markup()


def admin_design_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚪 Старт", callback_data="adm:design:start", style="primary")
    kb.button(text="👤 Профиль", callback_data="adm:design:profile", style="primary")
    kb.button(text="🛍 Магазин", callback_data="adm:design:shop", style="primary")
    kb.button(text="💰 Пополнение", callback_data="adm:design:deposit", style="primary")
    kb.button(text="ℹ️ Инфо", callback_data="adm:design:info", style="primary")
    kb.button(text="Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(3, 2, 1)
    return kb.as_markup()


def admin_settings_kb(tech_work: str, pay_enabled: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status = "🟢 ВЫКЛ" if tech_work == "0" else "🔴 ВКЛ"
    kb.button(text=f"Тех. работы: {status}", callback_data="adm:settings:tech", style="danger" if tech_work == "1" else "success")
    kb.button(text="Изменить суммы пополнения", callback_data="adm:settings:amounts", style="primary")
    kb.button(text="Изменить реф. процент", callback_data="adm:settings:ref", style="primary")
    kb.button(text="Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id=BACK_EMOJI)
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()


def admin_promos_kb(promos) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать", callback_data="adm:promos:add", style="success")
    for p in promos:
        kb.row(btn(f"🎟 {p['code']} · -{p['discount']}% · осталось {p['uses_left']}",
                   f"adm:promos:del:{p['code']}", style="danger"))
    kb.row(admin_back_kb().inline_keyboard[0][0])
    return kb.as_markup()


def admin_pending_deposits_kb(deposits) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in deposits:
        kb.row(
            btn(f"✅ #{d['id']} · {d['amount']} ₽", f"adm:dep:ok:{d['id']}", style="success"),
            btn("❌", f"adm:dep:no:{d['id']}", style="danger"),
        )
    kb.row(admin_back_kb().inline_keyboard[0][0])
    return kb.as_markup()
