import asyncpg
import os
import logging
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# .env читается до чтения DATABASE_URL
load_dotenv()

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
            DATABASE_URL, min_size=1, max_size=10,
            ssl="require" if use_ssl else None, timeout=10,
        )
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


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

        # Миграции для уже развёрнутой базы: IF NOT EXISTS ничего не ломает на чистой схеме
        await conn.execute("""
            ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by BIGINT;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_earned BIGINT DEFAULT 0;
            ALTER TABLE users ADD COLUMN IF NOT EXISTS active_promo TEXT;
            ALTER TABLE orders ADD COLUMN IF NOT EXISTS item_id INTEGER;
            ALTER TABLE products ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;
            CREATE TABLE IF NOT EXISTS deposits (
                id SERIAL PRIMARY KEY, user_id BIGINT, amount BIGINT, method TEXT DEFAULT 'crypto',
                status TEXT DEFAULT 'pending', invoice_id TEXT, created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP, expires_at TIMESTAMP
            );
            ALTER TABLE deposits ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
            CREATE INDEX IF NOT EXISTS deposits_status_idx ON deposits (status);
            CREATE INDEX IF NOT EXISTS product_items_sold_idx ON product_items (product_id, is_sold);
        """)

        # Дублирующаяся кнопка "Назад" из базы (теперь она генерируется автоматически)
        await conn.execute("DELETE FROM buttons WHERE button_key = 'back'")

        default_settings = [
            ("start_text", "Claude AI Store\n<tg-emoji emoji-id=\"5193119436621494267\">🏠</tg-emoji> Главное меню\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5458904472598095631\">👋</tg-emoji> С возвращением, <b>{name}</b>.\n<tg-emoji emoji-id=\"5769126056262898415\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n\nРазные продукты · API-ключи · Приватные сообщества"),
            ("start_photo", ""),
            ("profile_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429519697928301269\">👤</tg-emoji> Профиль\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n<tg-emoji emoji-id=\"5429154960715588692\">🛍️</tg-emoji> Всего потрачено: <b>{spent} ₽</b>\n<tg-emoji emoji-id=\"5429412504134525920\">🛒</tg-emoji> Покупок: <b>{purchases}</b>\n<tg-emoji emoji-id=\"5429256253224299845\">🔗</tg-emoji> Рефералов: <b>{refs} · заработано {ref_earned} ₽</b>\n\n<tg-emoji emoji-id=\"5427321817134051632\">🆔</tg-emoji> Ваш ID: <b>{user_id}</b>"),
            ("profile_photo", ""),
            ("shop_text", "Claude AI Store\n<tg-emoji emoji-id=\"5348475279960456198\">🛍</tg-emoji> Магазин\n<b>━━━━━━━━━━━━━</b>\n\nВыберите товар:"),
            ("shop_photo", ""),
            ("deposit_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429098361636560179\">💰</tg-emoji> Пополнение баланса\n<b>━━━━━━━━━━━━━</b>\n\nНа какую сумму пополнить баланс?\nОт 50₽."),
            ("deposit_photo", ""),
            ("info_text", "Claude AI Store\n<tg-emoji emoji-id=\"5348507247402040764\">ℹ️</tg-emoji> Информация\n<b>━━━━━━━━━━━━━</b>\n\nМы продаём цифровые товары: API-ключи, доступы и подписки.\nОплата и выдача происходят автоматически, сразу после оплаты.\n\n<tg-emoji emoji-id=\"5258513401784573443\">🛟</tg-emoji> Вопросы — в поддержку."),
            ("info_photo", ""),
            ("purchases_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429412504134525920\">🛒</tg-emoji> Мои покупки\n<b>━━━━━━━━━━━━━</b>"),
            ("promo_text", "Claude AI Store\n<tg-emoji emoji-id=\"5427375590124598857\">🎟</tg-emoji> Промокод\n<b>━━━━━━━━━━━━━</b>\n\nОтправьте промокод сообщением, чтобы активировать скидку."),
            ("ref_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429256253224299845\">🔗</tg-emoji> Реферальная программа\n<b>━━━━━━━━━━━━━</b>\n\nПриглашайте друзей и получайте <b>{percent}%</b> с каждого их пополнения.\n\n<tg-emoji emoji-id=\"5429519697928301269\">👤</tg-emoji> Приглашено: <b>{refs}</b>\n<tg-emoji emoji-id=\"5769126056262898415\">💰</tg-emoji> Заработано: <b>{earned} ₽</b>\n\nВаша ссылка:\n<code>{link}</code>"),
            ("choose_text", "Claude AI Store\n<tg-emoji emoji-id=\"5429098361636560179\">💰</tg-emoji> Пополнение баланса\n<b>━━━━━━━━━━━━━</b>\n\nСумма: <b>{amount}₽</b>\nID Заказа: <b>{order_id}</b>\n\nВыберите способ оплаты. Баланс зачислится автоматически."),
            ("crypto_text", "Claude AI Store\n<tg-emoji emoji-id=\"5426938074691056759\">💳</tg-emoji> Оплата криптой\n<b>━━━━━━━━━━━━━</b>\n\nПополнение: <b>{amount}₽</b>\nКомиссия CryptoBot {fee}%: +{fee_amount}₽\nК оплате: <b>{total}₽</b> (~${usd})\n\n<tg-emoji emoji-id=\"5426976819591032000\">⏳</tg-emoji> Ссылка действительна {minutes} минут.\n\n1. Нажмите «Оплатить» и переведите в USDT.\n2. Затем нажмите «Проверить оплату»."),
            ("crypto_expired_text", "Claude AI Store\n<tg-emoji emoji-id=\"5426938074691056759\">💳</tg-emoji> Оплата криптой\n<b>━━━━━━━━━━━━━</b>\n\nСрок действия счёта истёк.\nСоздайте новый счёт, чтобы оплатить."),
            ("support_url", "https://t.me/cxepy"),
            ("crypto_fee", "3"),
            ("crypto_ttl_minutes", "5"),
            ("tech_work", "0"),
            ("ref_percent", "5"),
            ("deposit_amounts", "100,250,500,1000,2500,5000"),
            ("min_deposit", "50"),
            ("max_deposit", "10000"),
        ]
        # DO NOTHING вместо DO UPDATE — правки из админки не затираются при рестарте
        for k, v in default_settings:
            await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", k, v)

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
        ]
        for b in default_buttons:
            await conn.execute("""
                INSERT INTO buttons (screen, button_key, text, callback_data, url, style, emoji_id, row_num, position)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (button_key) DO NOTHING
            """, *b)
        # Кнопка каталога на экране магазина больше не нужна: товары выводятся списком из базы
        await conn.execute("DELETE FROM buttons WHERE button_key = 'api'")


async def get_setting(key: str, default: str = "") -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
        return row['value'] if row and row['value'] is not None else default


async def set_setting(key: str, value: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", key, value)


async def register_user(user_id: int, first_name: str, username: Optional[str], referred_by: Optional[int] = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # referred_by пишется только при первой регистрации, иначе реферера можно переписать через /start
        await conn.execute("""
            INSERT INTO users (user_id, first_name, username, referred_by) VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE SET first_name = EXCLUDED.first_name, username = EXCLUDED.username
        """, user_id, first_name, username, referred_by)


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)
        return dict(row) if row else None


async def add_balance(user_id: int, amount: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", amount, user_id)


async def set_ban(user_id: int, status: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_banned = $1 WHERE user_id = $2", status, user_id)


async def count_users() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users") or 0


async def get_users(limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users ORDER BY reg_date DESC LIMIT $1 OFFSET $2", limit, offset)
        return [dict(r) for r in rows]


async def count_refs(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM users WHERE referred_by = $1", user_id) or 0


async def get_active_products() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products WHERE is_active = 1 ORDER BY sort_order, id")
        return [dict(r) for r in rows]


async def get_all_products() -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM products ORDER BY id")
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
    clean = [i.strip() for i in items if i and i.strip()]
    if not clean:
        return 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in clean:
                await conn.execute("INSERT INTO product_items (product_id, content) VALUES ($1, $2)", product_id, item)
    return len(clean)


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
            user = await conn.fetchrow("SELECT balance, is_banned FROM users WHERE user_id = $1 FOR UPDATE", user_id)
            if not user:
                return {"success": False, "error": "Юзер не найден"}

            prod = await conn.fetchrow("SELECT price, is_active FROM products WHERE id = $1", product_id)
            if not prod or not prod['is_active']:
                return {"success": False, "error": "Товар недоступен"}

            final_price = int(prod['price'] * (100 - discount) / 100)
            if user['balance'] < final_price:
                return {"success": False, "error": "Недостаточно средств", "price": final_price}

            # FOR UPDATE на самой позиции: параллельная покупка не сможет выдать тот же ключ
            item = await conn.fetchrow(
                "SELECT id, content FROM product_items WHERE product_id = $1 AND is_sold = 0 ORDER BY id LIMIT 1 FOR UPDATE",
                product_id,
            )
            if not item:
                return {"success": False, "error": "Нет в наличии"}

            await conn.execute("UPDATE users SET balance = balance - $1, total_spent = total_spent + $1, purchases_count = purchases_count + 1 WHERE user_id = $2", final_price, user_id)
            await conn.execute("UPDATE product_items SET is_sold = 1, sold_to = $1, sold_date = CURRENT_TIMESTAMP WHERE id = $2", user_id, item['id'])
            await conn.execute("INSERT INTO orders (user_id, product_id, price, item_id) VALUES ($1, $2, $3, $4)", user_id, product_id, final_price, item['id'])

            return {"success": True, "content": item['content'], "balance": user['balance'] - final_price, "price": final_price}


async def get_all_users_ids() -> List[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE is_banned = 0")
        return [r['user_id'] for r in rows]


async def get_user_orders(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.id, o.price, o.order_date, p.name, pi.content
            FROM orders o
            LEFT JOIN products p ON p.id = o.product_id
            LEFT JOIN product_items pi ON pi.id = o.item_id
            WHERE o.user_id = $1 ORDER BY o.id DESC LIMIT $2
        """, user_id, limit)
        return [dict(r) for r in rows]


async def get_recent_orders(limit: int = 15) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT o.id, o.user_id, o.price, o.order_date, p.name
            FROM orders o LEFT JOIN products p ON p.id = o.product_id
            ORDER BY o.id DESC LIMIT $1
        """, limit)
        return [dict(r) for r in rows]


async def get_stats() -> Dict[str, int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
        sales = await conn.fetchrow("SELECT COALESCE(SUM(price), 0) as total FROM orders")
        orders = await conn.fetchrow("SELECT COUNT(*) as cnt FROM orders")
        topped = await conn.fetchrow("SELECT COALESCE(SUM(amount), 0) as total FROM deposits WHERE status = 'paid'")
        pending = await conn.fetchrow("SELECT COUNT(*) as cnt FROM deposits WHERE status = 'pending'")
        return {"users": users['cnt'], "sales": sales['total'], "orders": orders['cnt'],
                "topped": topped['total'], "pending": pending['cnt']}


async def create_deposit(user_id: int, amount: int, method: str = "crypto", invoice_id: Optional[str] = None) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO deposits (user_id, amount, method, invoice_id) VALUES ($1, $2, $3, $4) RETURNING id",
            user_id, amount, method, invoice_id,
        )


async def set_deposit_invoice(deposit_id: int, invoice_id: str, expires_at=None, method: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE deposits SET invoice_id = $1, expires_at = COALESCE($2, expires_at), "
            "method = COALESCE($3, method) WHERE id = $4",
            invoice_id, expires_at, method, deposit_id,
        )


async def get_deposit(deposit_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM deposits WHERE id = $1", deposit_id)
        return dict(row) if row else None


async def mark_deposit_paid(deposit_id: int, ref_percent: int = 0) -> Optional[Dict[str, Any]]:
    """Идемпотентно закрывает депозит и начисляет баланс. None — если уже был оплачен."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            dep = await conn.fetchrow("SELECT * FROM deposits WHERE id = $1 FOR UPDATE", deposit_id)
            if not dep or dep['status'] == 'paid':
                return None
            await conn.execute("UPDATE deposits SET status = 'paid', paid_at = CURRENT_TIMESTAMP WHERE id = $1", deposit_id)
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE user_id = $2", dep['amount'], dep['user_id'])

            ref = None
            if ref_percent > 0:
                ref_id = await conn.fetchval("SELECT referred_by FROM users WHERE user_id = $1", dep['user_id'])
                if ref_id and ref_id != dep['user_id']:
                    bonus = int(dep['amount'] * ref_percent / 100)
                    if bonus > 0:
                        await conn.execute("UPDATE users SET balance = balance + $1, ref_earned = ref_earned + $1 WHERE user_id = $2", bonus, ref_id)
                        ref = {"user_id": ref_id, "amount": bonus}

            balance = await conn.fetchval("SELECT balance FROM users WHERE user_id = $1", dep['user_id'])
            return {"deposit": dict(dep), "balance": balance, "ref": ref}


async def cancel_deposit(deposit_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE deposits SET status = 'canceled' WHERE id = $1 AND status = 'pending'", deposit_id)


async def get_deposits(status: Optional[str] = None, limit: int = 15) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM deposits WHERE status = $1 ORDER BY id DESC LIMIT $2", status, limit)
        else:
            rows = await conn.fetch("SELECT * FROM deposits ORDER BY id DESC LIMIT $1", limit)
        return [dict(r) for r in rows]


async def create_promo(code: str, discount: int, uses: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO promocodes (code, discount, uses_left) VALUES ($1, $2, $3) ON CONFLICT (code) DO UPDATE SET discount = EXCLUDED.discount, uses_left = EXCLUDED.uses_left",
            code, discount, uses,
        )


async def get_promo(code: str) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM promocodes WHERE code = $1", code)
        return dict(row) if row else None


async def delete_promo(code: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM promocodes WHERE code = $1", code)


async def list_promos(limit: int = 20) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM promocodes ORDER BY code LIMIT $1", limit)
        return [dict(r) for r in rows]


async def set_user_promo(user_id: int, code: Optional[str]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET active_promo = $1 WHERE user_id = $2", code, user_id)


async def get_user_promo(user_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT p.* FROM users u JOIN promocodes p ON p.code = u.active_promo
            WHERE u.user_id = $1
        """, user_id)
        return dict(row) if row else None


async def consume_promo(user_id: int):
    """Списывает использование промокода и снимает его с пользователя."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            code = await conn.fetchval("SELECT active_promo FROM users WHERE user_id = $1 FOR UPDATE", user_id)
            if not code:
                return
            await conn.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = $1 AND uses_left > 0", code)
            await conn.execute("UPDATE users SET active_promo = NULL WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM promocodes WHERE uses_left <= 0")


async def get_buttons(screen: str) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM buttons WHERE screen = $1 AND is_active = 1 ORDER BY row_num, position", screen)
        return [dict(r) for r in rows]


async def update_button(button_key: str, **kwargs):
    allowed = ['text', 'callback_data', 'url', 'style', 'emoji_id', 'row_num', 'position', 'is_active']
    pool = await get_pool()
    async with pool.acquire() as conn:
        for key, value in kwargs.items():
            if key in allowed:
                await conn.execute(f"UPDATE buttons SET {key} = $1 WHERE button_key = $2", value, button_key)
