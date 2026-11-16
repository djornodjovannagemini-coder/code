import asyncio, os, re
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import database as db
import addin

ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
router = Router()
def is_adm(uid): return uid in ADMIN_IDS

class Adm(StatesGroup):
    p_name = State(); p_desc = State(); p_price = State(); p_type = State(); p_items = State()
    u_id = State(); u_amount = State()
    d_text = State(); d_photo = State()
    b_msg = State()
    btn_key = State(); btn_text = State(); btn_style = State(); btn_emoji = State()

# ... (хэндлеры товаров, юзеров, рассылки остаются без изменений, кроме адаптации под asyncpg) ...

@router.callback_query(F.data == "adm:design")
async def adm_design(call: CallbackQuery):
    await call.answer()
    if is_adm(call.from_user.id):
        await call.message.edit_text("🎨 <b>Оформление</b>\nВыберите экран:", reply_markup=addin.admin_design_kb())

@router.callback_query(F.data.startswith("adm:design:"))
async def design_screen(call: CallbackQuery):
    await call.answer()
    screen = call.data.split(":")[2]
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Текст экрана", callback_data=f"adm:ed:t:{screen}", style="primary")
    kb.button(text="🖼 Картинка", callback_data=f"adm:ed:p:{screen}", style="primary")
    kb.button(text="🔘 Кнопки", callback_data=f"adm:ed:b:{screen}", style="primary")
    kb.button(text="⬅️ Назад", callback_data="adm:design", style="danger")
    kb.adjust(1, 1, 1, 1)
    await call.message.edit_text(f"Настройка экрана <b>{screen}</b>:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("adm:ed:t:"))
async def edit_text_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen, edit_type="text")
    await call.message.edit_text(
        f"Отправьте новый текст для <b>{screen}</b>.\n"
        f"💡 <i>Если вы пришлёте премиум-эмодзи, бот автоматически подставит его ID.</i>\n"
        f"Чтобы оставить старый, отправьте <code>-</code>."
    )
    await state.set_state(Adm.d_text)

@router.message(Adm.d_text)
async def process_new_text(msg: Message, state: FSMContext):
    data = await state.get_data()
    screen = data['screen']
    
    if msg.text == "-":
        await msg.answer("Текст оставлен без изменений.")
    else:
        new_text = msg.text or msg.caption or ""
        # Автопоиск премиум-эмодзи
        if msg.entities:
            for entity in msg.entities:
                if entity.type == "custom_emoji":
                    emoji_char = new_text[entity.offset:entity.offset + entity.length]
                    new_text = new_text.replace(emoji_char, f'<tg-emoji emoji-id="{entity.custom_emoji_id}">{emoji_char}</tg-emoji>', 1)
        
        await db.set_setting(f"{screen}_text", new_text)
        await msg.answer("✅ Текст обновлен!")
        
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад", callback_data=f"adm:design:{screen}", style="danger")
    await msg.answer("Вернуться в меню?", reply_markup=kb.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("adm:ed:p:"))
async def edit_photo_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    screen = call.data.split(":")[3]
    await state.update_data(screen=screen, edit_type="photo")
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
    kb.button(text="⬅️ Назад", callback_data=f"adm:design:{screen}", style="danger")
    await msg.answer("Вернуться в меню?", reply_markup=kb.as_markup())
    await state.clear()

@router.callback_query(F.data.startswith("adm:ed:b:"))
async def edit_buttons_start(call: CallbackQuery):
    await call.answer()
    screen = call.data.split(":")[3]
    buttons = await db.get_buttons(screen)
    
    kb = InlineKeyboardBuilder()
    for b in buttons:
        kb.button(text=f"[{b['button_key']}] {b['text']}", callback_data=f"adm:btn:{b['button_key']}", style="primary")
    kb.button(text="⬅️ Назад", callback_data=f"adm:design:{screen}", style="danger")
    kb.adjust(1)
    
    await call.message.edit_text(f"Кнопки экрана <b>{screen}</b>:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("adm:btn:"))
async def edit_single_button(call: CallbackQuery):
    await call.answer()
    key = call.data.split(":")[2]
    await call.message.edit_text(
        f"Редактирование кнопки <b>{key}</b>.\n"
        "Отправьте новый текст кнопки (или <code>-</code> чтобы оставить):"
    )
    # Здесь можно добавить FSM для изменения текста, цвета, эмодзи и т.д.
    # Для краткости ответа, этот блок можно расширить по аналогии с текстом.
