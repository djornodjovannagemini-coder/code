from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
import database as db

async def build_keyboard_from_db(screen: str, back_screen: str = None) -> InlineKeyboardMarkup:
    buttons_data = await db.get_buttons(screen)
    kb = InlineKeyboardBuilder()
    
    # Группируем по строкам
    rows = {}
    for btn in buttons_data:
        r = btn['row_num']
        if r not in rows: rows[r] = []
        rows[r].append(btn)
        
    for r in sorted(rows.keys()):
        row_buttons = []
        for b in rows[r]:
            btn_obj = InlineKeyboardButton(
                text=b['text'],
                callback_data=b['callback_data'] if b['callback_data'] else None,
                url=b['url'] if b['url'] else None,
                style=b['style'],
                icon_custom_emoji_id=b['emoji_id'] if b['emoji_id'] else None
            )
            row_buttons.append(btn_obj)
        kb.row(*row_buttons)
        
    # Если нужна кнопка "Назад"
    if back_screen:
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back_screen, style="danger", icon_custom_emoji_id="5888484185261216745"))
        
    return kb.as_markup()

# Юзерские клавиатуры (теперь они будут асинхронными)
async def main_menu_kb() -> InlineKeyboardMarkup:
    return await build_keyboard_from_db("main")

async def profile_kb() -> InlineKeyboardMarkup:
    return await build_keyboard_from_db("profile", back_screen="menu:back")

async def shop_menu_kb() -> InlineKeyboardMarkup:
    return await build_keyboard_from_db("shop", back_screen="menu:back")

# Админские клавиатуры (можно оставить статическими, так как они для тебя)
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
    kb.button(text="⬅️ Выход", callback_data="menu:back", style="danger", icon_custom_emoji_id="5888484185261216745")
    kb.adjust(2, 2, 2, 2, 2, 1)
    return kb.as_markup()

def admin_back_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data="adm:menu", style="danger", icon_custom_emoji_id="5888484185261216745")
    return kb.as_markup()

def admin_products_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить", callback_data="adm:prod:add", style="success")
    kb.button(text="👁 Скрыть/Показать", callback_data="adm:prod:toggle", style="primary")
    kb.button(text="🗑 Удалить", callback_data="adm:prod:del", style="danger")
    kb.button(text="⬅️ Назад", callback_data="adm:menu", style="danger")
    kb.adjust(1, 1, 1, 1)
    return kb.as_markup()

def admin_users_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Изменить баланс", callback_data="adm:users:bal", style="success")
    kb.button(text="⛔️ Забанить / Разбанить", callback_data="adm:users:ban", style="danger")
    kb.button(text="⬅️ Назад", callback_data="adm:menu", style="danger")
    kb.adjust(1, 1, 1)
    return kb.as_markup()

def admin_design_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🚪 Старт", callback_data="adm:design:start", style="primary")
    kb.button(text="👤 Профиль", callback_data="adm:design:profile", style="primary")
    kb.button(text="🛍 Магазин", callback_data="adm:design:shop", style="primary")
    kb.button(text="⬅️ Назад", callback_data="adm:menu", style="danger")
    kb.adjust(3, 1)
    return kb.as_markup()

def admin_settings_kb(tech_work: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    status = "🟢 ВЫКЛ" if tech_work == "0" else "🔴 ВКЛ"
    kb.button(text=f"Тех. работы: {status}", callback_data="adm:settings:tech", style="danger" if tech_work == "1" else "success")
    kb.button(text="⬅️ Назад", callback_data="adm:menu", style="danger")
    kb.adjust(1, 1)
    return kb.as_markup()
