import asyncpg
import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("❌ КРИТИЧЕСКАЯ ОШИБКА: DATABASE_URL не задан в Variables!")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

use_ssl = "railway.internal" not in DATABASE_URL
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            ssl="require" if use_ssl else None,
            timeout=10
        )
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY, first_name TEXT, username TEXT,
                balance BIGINT DEFAULT 0, total_spent BIGINT DEFAULT 0, purchases_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0, reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY, name TEXT, description TEXT, price BIGINT, item_type TEXT DEFAULT 'text', is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS product_items (
                id SERIAL PRIMARY KEY, product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
                content TEXT, is_sold INTEGER DEFAULT 0, sold_to BIGINT, sold_date TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY, user_id BIGINT, product_id INTEGER, price BIGINT, order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS promocodes (code TEXT PRIMARY KEY, discount INTEGER, uses_left INTEGER);
            CREATE TABLE IF NOT EXISTS buttons (
                id SERIAL PRIMARY KEY, screen TEXT, button_key TEXT UNIQUE, text TEXT,
                callback_data TEXT, url TEXT, style TEXT DEFAULT 'primary', emoji_id TEXT,
                row_num INTEGER, position INTEGER, is_active INTEGER DEFAULT 1
            );
        """)
        
        # 1. ВОЗВРАЩАЕМ ТЕКСТЫ С ПРЕМИУМ-ЭМОДЗИ (Принудительное обновление)
        default_settings = [
            ("start_text", "Claude AI Store\n<tg-emoji emoji-id=\"5193119436621494267\">🏠</tg-emoji> Главное меню\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5458904472598095631\">👋</tg-emoji> С возвращением, <b>{name}</b>.\n<tg-emoji emoji-id=\"5769126056262898415\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n\nРазные продукты · API-ключи · Приватные сообщества"),
            ("start_photo", ""),
            ("profile_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429519697928301269\">👤</tg-emoji> Профиль\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n<tg-emoji emoji-id=\"5429154960715588692\">🛍️</tg-emoji> Всего потрачено: <b>{spent} ₽</b>\n<tg-emoji emoji-id=\"5429412504134525920\">🛒</tg-emoji> Покупок: <b>{purchases}</b>\n<tg-emoji emoji-id=\"5429256253224299845\">🔗</tg-emoji> Рефералов: <b>{refs} · заработано {ref_earned} ₽</b>\n\n<tg-emoji emoji-id=\"5427321817134051632\">🆔</tg-emoji> Ваш ID: <b>{user_id}</b>"),
            ("profile_photo", ""),
            ("shop_text", "Claude AI Store\n<tg-emoji emoji-id=\"5348475279960456198\">🛍</tg-emoji> Магазин\n<b>━━━━━━━━━━━━━</b>\n\nВыберите категорию:"),
            ("shop_photo", ""),
            ("tech_work", "0")
        ]
        for k, v in default_settings:
            await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", k, v)
        
        # 2. ВОЗВРАЩАЕМ КНОПКИ С ЭМОДЗИ
        default_buttons = [
            ('main', 'profile', 'Профиль', 'menu:profile', None, 'primary', '6032693626394382504', 1, 1),
            ('main', 'shop', 'Магазин', 'menu:shop', None, 'primary', '5348475279960456198', 1, 2),
            ('main', 'info', 'Информация', 'menu:info', None, 'success', '5348507247402040764', 2, 1),
            ('main', 'channel', 'Канал', None, 'https://t.me/anthropc_claude', 'success', '5260268501515377807', 2, 2),
            ('main', 'support', 'Поддержка', None, 'https://t.me/cxepy', 'danger', '5258513401784573443', 3, 1),
            ('profile', 'deposit', 'Пополнить баланс', 'profile:deposit', None, 'success', '5429098361636560179', 1, 1),
            ('profile', 'purchases', 'Покупки', 'profile:purchases', None, 'primary', '5429412504134525920', 2, 1),
            ('profile', 'promo', 'Промокод', 'profile:promo', None, 'primary', '5427375590124598857', 2, 2),
            ('profile', 'ref', 'Рефералка', 'profile:referral', None, 'primary', '5429256253224299845', 3, 1),
            ('profile', 'back', 'Назад', 'menu:back', None, 'danger', '5888484185261216745', 3, 2),
            ('shop', 'api', 'API-ключи', 'shop:catalog', None, 'success', '5427112068111184025', 1, 1),
            ('shop', 'back', 'Назад', 'menu:back', None, 'danger', '5888484185261216745', 2, 1)
        ]
        for b in default_buttons:
            await conn.execute("""
                INSERT INTO buttons (screen, button_key, text, callback_data, url, style, emoji_id, row_num, position) 
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (button_key) DO UPDATE SET 
                text = EXCLUDED.text, callback_data = EXCLUDED.callback_data, url = EXCLUDED.url, 
                style = EXCLUDED.style, emoji_id = EXCLUDED.emoji_id, row_num = EXCLUDED.row_num, position = EXCLUDED.position
            """, *b)

async def get_setting(key: str, default: str = "") -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row['value'] if row else default

async def set_setting(key: str, value: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", key, value)

async def register_user(user_id: int, first_name: str, username: Optional[str]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO users (user_id, first_name, username) VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET first_name = EXCLUDED.first_name, username = EXCLUDED.username
        """, user_id, first_name, username)

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None

async def get_active_products() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products WHERE is_active = 1")
        return [dict(r) for r in rows]

async def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM products WHERE id = $1", product_id)
        return dict(row) if row else None

async def get_product_stock(product_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM product_items WHERE product_id = $1 AND is_sold = 0", product_id)
        return row['cnt'] if row else 0

async def add_product(name: str, desc: str, price: int, item_type: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("INSERT INTO products (name, description, price, item_type) VALUES ($1, $2, $3, $4) RETURNING id", name, desc, price, item_type)
        return row['id']

async def add_product_items(product_id: int, items: List[str]) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in items:
                if item.strip():
                    await conn.execute("INSERT INTO product_items (product_id, content) VALUES ($1, $2)", product_id, item.strip())
        return len(items)

async def toggle_product(product_id: int, status: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE products SET is_active = $1 WHERE id = $2", status, product_id)

async def delete_product(product_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM products WHERE id = $1", product_id)

async def buy_product(user_id: int, product_id: int, discount: int = 0) -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1 FOR UPDATE", user_id)
            if not user: return {"success": False, "error": "Юзер не найден"}
            
            prod = await conn.fetchrow("SELECT price, is_active FROM products WHERE id = $1", product_id)
            if not prod or not prod['is_active']: return {"success": False, "error": "Товар недоступен"}
            
            final_price = int(prod['price'] * (1 - discount / 100))
            if user['balance'] < final_price: return {"success": False, "error": "Недостаточно средств"}
            
            item = await conn.fetchrow("SELECT id, content FROM product_items WHERE product_id = $1 AND is_sold = 0 LIMIT 1 FOR UPDATE", product_id)
            if not item: return {"success": False, "error": "Нет в наличии"}
            
            await conn.execute("UPDATE users SET balance = balance - $1, total_spent = total_spent + $1, purchases_count = purchases_count + 1 WHERE user_id = $2", final_price, user_id)
            await conn.execute("UPDATE product_items SET is_sold = 1, sold_to = $1, sold_date = CURRENT_TIMESTAMP WHERE id = $2", user_id, item['id'])
            await conn.execute("INSERT INTO orders (user_id, product_id, price) VALUES ($1, $2, $3)", user_id, product_id, final_price)
            
            return {"success": True, "content": item['content'], "balance": user['balance'] - final_price, "price": final_price}

async def get_all_users_ids() -> List[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned = 0")
        return [r['user_id'] for r in rows]

async def get_stats() -> Dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
        sales = await conn.fetchrow("SELECT COALESCE(SUM(price), 0) as total FROM orders")
        orders = await conn.fetchrow("SELECT COUNT(*) as cnt FROM orders")
        return {"users": users['cnt'], "sales": sales['total'], "orders": orders['cnt']}

async def get_buttons(screen: str) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM buttons WHERE screen = $1 AND is_active = 1 ORDER BY row_num, position", screen)
        return [dict(r) for r in rows]

async def update_button(button_key: str, **kwargs):
    pool = await get_pool()
    async with pool.acquire() as conn:
        for key, value in kwargs.items():
            if key in ['text', 'callback_data', 'url', 'style', 'emoji_id', 'row_num', 'position', 'is_active']:
                await conn.execute(f"UPDATE buttons SET {key} = $1 WHERE button_key = $2", value, button_key)
