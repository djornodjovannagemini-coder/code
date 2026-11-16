from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import database as db

# Эмодзи по умолчанию — используются только для динамических рядов
# (списки товаров, суммы пополнения и прочее, что нельзя задать статикой в базе).
BACK_EMOJI = "5888484185261216745"
CUSTOM_AMOUNT_EMOJI = "5427016470729127056"
PURCHASES_EMOJI = "5429412504134525920"
SHOP_EMOJI = "5348475279960456198"
BALANCE_EMOJI = "5258204546391351475"
MONEY_EMOJI = "5769126056262898415"
DEPOSIT_EMOJI = "5429098361636560179"
PROMO_EMOJI = "5427375590124598857"
REF_EMOJI = "5429256253224299845"
STOCK_EMOJI = "5429154960715588692"
PRODUCT_EMOJI = "5429250347644262814"


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _fmt(value, params):
    if not value or not params:
        return value
    try:
        return value.format_map(_SafeDict(params))
    except (ValueError, IndexError):
        return value


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


async def _rows_from_db(screen: str, params: dict = None) -> dict:
    rows = {}
    for b in await db.get_buttons(screen):
        callback = _fmt(b['callback_data'], params) or None
        url = _fmt(b['url'], params) or None
        if not callback and not url:
            continue
        rows.setdefault(b['row_num'], []).append(btn(
            text=_fmt(b['text'], params),
            callback_data=callback,
            url=url,
            style=b['style'] or "primary",
            emoji=b['emoji_id'] or None,
        ))
    return rows


async def kb(screen: str, params: dict = None, dynamic=None) -> InlineKeyboardMarkup:
    """Клавиатура экрана: статические кнопки из базы + динамические ряды.

    dynamic — список пар (номер_ряда, список кнопок), чтобы динамика встала
    на нужное место между кнопками из базы.
    """
    rows = await _rows_from_db(screen, params)
    for row, buttons in (dynamic or []):
        rows.setdefault(row, []).extend(buttons)
    builder = InlineKeyboardBuilder()
    for r in sorted(rows):
        builder.row(*rows[r])
    return builder.as_markup()


# ==================== КЛИЕНТ ====================
async def main_menu_kb() -> InlineKeyboardMarkup:
    return await kb("main")


async def profile_kb() -> InlineKeyboardMarkup:
    return await kb("profile")


async def shop_menu_kb(products=None) -> InlineKeyboardMarkup:
    dynamic = []
    for i, p in enumerate(products or [], start=1):
        dynamic.append((i, [btn(f"{p['name']} · {p['price']} ₽", f"shop:item:{p['id']}",
                                style="primary", emoji=SHOP_EMOJI)]))
    return await kb("shop", dynamic=dynamic)


async def deposit_kb(amounts) -> InlineKeyboardMarkup:
    dynamic = []
    for i in range(0, len(amounts), 2):
        row = i // 2 + 1
        dynamic.append((row, [btn(f"{a} ₽", f"dep:amount:{a}", style="primary") for a in amounts[i:i + 2]]))
    return await kb("deposit", dynamic=dynamic)


async def cancel_kb() -> InlineKeyboardMarkup:
    return await kb("cancel")


async def choose_payment_kb(dep_id: int, support_url: str) -> InlineKeyboardMarkup:
    return await kb("choose_payment", {"id": dep_id, "support": support_url})


async def crypto_pay_kb(url: str, dep_id: int) -> InlineKeyboardMarkup:
    return await kb("crypto_pay", {"url": url or "", "id": dep_id})


async def crypto_expired_kb(dep_id: int) -> InlineKeyboardMarkup:
    return await kb("crypto_expired", {"id": dep_id})


async def product_kb(product_id: int, can_buy: bool) -> InlineKeyboardMarkup:
    return await kb("product" if can_buy else "product_back", {"id": product_id})


async def product_link_kb(product_id: int) -> InlineKeyboardMarkup:
    return await kb("announce", {"id": product_id})


async def simple_kb(screen: str) -> InlineKeyboardMarkup:
    return await kb(screen)


# ==================== АДМИНКА ====================
async def admin_main_kb() -> InlineKeyboardMarkup:
    return await kb("adm_main")


async def admin_back_kb() -> InlineKeyboardMarkup:
    return await kb("adm_back")


async def admin_products_kb() -> InlineKeyboardMarkup:
    return await kb("adm_products")


async def admin_product_pick_kb(products, action: str) -> InlineKeyboardMarkup:
    dynamic = []
    for i, p in enumerate(products[:8], start=1):
        mark = "🟢" if p['is_active'] else "🔴"
        dynamic.append((i, [btn(f"{mark} {p['name']} · {p['price']} ₽", f"adm:prod:{action}:{p['id']}",
                                style="primary")]))
    return await kb("adm_product_pick", dynamic=dynamic)


async def admin_users_kb() -> InlineKeyboardMarkup:
    return await kb("adm_users")


async def admin_user_ban_kb(user) -> InlineKeyboardMarkup:
    if user['is_banned']:
        row = [btn("Разбанить", f"adm:users:unban:{user['user_id']}", style="success")]
    else:
        row = [btn("Забанить", f"adm:users:ban:{user['user_id']}", style="danger")]
    return await kb("adm_user_ban", dynamic=[(1, row)])


async def admin_design_kb() -> InlineKeyboardMarkup:
    return await kb("adm_design")


async def admin_settings_kb(tech_work: str, pay_enabled: bool) -> InlineKeyboardMarkup:
    kb_obj = await kb("adm_settings")
    status = "🟢 ВЫКЛ" if tech_work == "0" else "🔴 ВКЛ"
    for row in kb_obj.inline_keyboard:
        for b in row:
            if b.callback_data == "adm:settings:tech":
                b.text = f"Тех. работы: {status}"
                b.style = "danger" if tech_work == "1" else "success"
    return kb_obj


async def admin_promos_kb(promos) -> InlineKeyboardMarkup:
    dynamic = []
    for i, p in enumerate(promos[:8], start=2):
        dynamic.append((i, [btn(f"🎟 {p['code']} · -{p['discount']}% · осталось {p['uses_left']}",
                                f"adm:promos:del:{p['code']}", style="danger")]))
    return await kb("adm_promos", dynamic=dynamic)


async def admin_pending_deposits_kb(deposits) -> InlineKeyboardMarkup:
    dynamic = []
    for i, d in enumerate(deposits[:8], start=1):
        dynamic.append((i, [
            btn(f"✅ #{d['id']} · {d['amount']} ₽", f"adm:dep:ok:{d['id']}", style="success"),
            btn("❌", f"adm:dep:no:{d['id']}", style="danger"),
        ]))
    return await kb("adm_finance", dynamic=dynamic)
