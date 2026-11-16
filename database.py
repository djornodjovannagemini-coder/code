import asyncpg
import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Получаем URL базы данных из переменных окружения Railway
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ КРИТИЧЕСКАЯ ОШИБКА: DATABASE_URL не задан в Variables!")

# Railway иногда выдает postgres:// вместо postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Для внутренних подключений Railway (postgres.railway.internal) SSL не требуется
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
        # Создание таблиц
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                balance BIGINT DEFAULT 0,
                total_spent BIGINT DEFAULT 0,
                purchases_count INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name TEXT,
                description TEXT,
                price BIGINT,
                item_type TEXT DEFAULT 'text',
                is_active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS product_items (
                id SERIAL PRIMARY KEY,
                product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
                content TEXT,
                is_sold INTEGER DEFAULT 0,
                sold_to BIGINT,
                sold_date TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                product_id INTEGER,
                price BIGINT,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount INTEGER,
                uses_left INTEGER
            );
            CREATE TABLE IF NOT EXISTS buttons (
                id SERIAL PRIMARY KEY,
                screen TEXT,
                button_key TEXT UNIQUE,
                text TEXT,
                callback_data TEXT,
                url TEXT,
                style TEXT DEFAULT 'primary',
                emoji_id TEXT,
                row_num INTEGER,
                position INTEGER,
                is_active INTEGER DEFAULT 1
            );
        """)
        
        # Базовые настройки экранов
        default_settings = [
            ("start_text", "Claude AI Store\n<tg-emoji emoji-id=\"5193119436621494267\">🏠</tg-emoji> Главное меню\n<b>━━━━━━━━━━━━━</b>\n\n👋 С возвращением, <b>{name}</b>.\n💰 Баланс: <b>{balance} ₽</b>\n\nРазные продукты · API-ключи · Приватные сообщества"),
            ("start_photo", ""),
            ("profile_text", "👤 Профиль\n<b>━━━━━━━━━━━━━</b>\n\n💰 Баланс: <b>{balance} ₽</b>\n🛍 Всего потрачено: <b>{spent} ₽</b>\n🛒 Покупок: <b>{purchases}</b>\n🆔 Ваш ID: <b>{user_id}</b>"),
            ("profile_photo", ""),
            ("shop_text", "🛍 <b>Магазин</b>\nВыберите раздел:"),
            ("shop_photo", ""),
            ("tech_work", "0")
        ]
        for k, v in default_settings:
            await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", k, v)
        
        # Дефолтные кнопки для главного меню
        await conn.execute("""
            INSERT INTO buttons (screen, button_key, text, callback_data, url, style, emoji_id, row_num, position) 
            VALUES 
            ('main', 'profile', 'Профиль', 'menu:profile', NULL, 'primary', '6032693626394382504', 1, 1),
            ('main', 'shop', 'Магазин', 'menu:shop', NULL, 'primary', '5348475279960456198', 1, 2),
            ('main', 'info', 'Информация', 'menu:info', NULL, 'success', '5348507247402040764', 2, 1),
            ('main', 'channel', 'Канал', NULL, 'https://t.me/anthropc_claude', 'success', '5260268501515377807', 2, 2),
            ('main', 'support', 'Поддержка', NULL, 'https://t.me/cxepy', 'danger', '5258513401784573443', 3, 1)
            ON CONFLICT (button_key) DO NOTHING
        """)

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
            # Блокируем строку пользователя, чтобы избежать списания дважды
            user = await conn.fetchrow("SELECT balance FROM users WHERE user_id = $1 FOR UPDATE", user_id)
            if not user: return {"success": False, "error": "Юзер не найден"}
            
            prod = await conn.fetchrow("SELECT price, is_active FROM products WHERE id = $1", product_id)
            if not prod or not prod['is_active']: return {"success": False, "error": "Товар недоступен"}
            
            final_price = int(prod['price'] * (1 - discount / 100))
            if user['balance'] < final_price: return {"success": False, "error": "Недостаточно средств"}
            
            # Блокируем ключ, чтобы два человека не купили один и тот же
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
            # Защита от SQL-инъекций через ключи (только разрешенные колонки)
            if key in ['text', 'callback_data', 'url', 'style', 'emoji_id', 'row_num', 'position', 'is_active']:
                await conn.execute(f"UPDATE buttons SET {key} = $1 WHERE button_key = $2", value, button_key)
