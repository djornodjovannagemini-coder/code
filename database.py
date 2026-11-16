import aiosqlite
from typing import Optional, Dict, Any, List

DB_PATH = "bot.db"

async def init_db():
    """Создает таблицы и добавляет дефолтные настройки при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                balance INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                purchases_count INTEGER DEFAULT 0,
                ref_count INTEGER DEFAULT 0,
                ref_earned INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                reg_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица настроек экранов (тексты, баннеры)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                screen_name TEXT PRIMARY KEY,
                text TEXT,
                photo_id TEXT
            )
        """)
        
        # Таблица товаров
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                price INTEGER,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Таблица ключей (склад)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS product_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                key_text TEXT,
                is_sold INTEGER DEFAULT 0,
                sold_to INTEGER,
                sold_date TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        """)
        
        # Таблица заказов (история)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                key_id INTEGER,
                price INTEGER,
                order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Добавляем дефолтные тексты, если их нет
        default_settings = [
            ("start", "Claude AI Store\n<tg-emoji emoji-id=\"5193119436621494267\">🏠</tg-emoji> Главное меню\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5458904472598095631\">👋</tg-emoji> С возвращением, <b>{name}</b>.\n<tg-emoji emoji-id=\"5769126056262898415\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n\nРазные продукты · API-ключи · Приватные сообщества", None),
            ("profile", "Claude AI Store\n<tg-emoji emoji-id=\"5429519697928301269\">👤</tg-emoji> Профиль\n<b>━━━━━━━━━━━━━</b>\n\n<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> Баланс: <b>{balance} ₽</b>\n<tg-emoji emoji-id=\"5429154960715588692\">🛍️</tg-emoji> Всего потрачено: <b>{spent} ₽</b>\n<tg-emoji emoji-id=\"5429412504134525920\">🛒</tg-emoji> Покупок: <b>{purchases}</b>\n<tg-emoji emoji-id=\"5429256253224299845\">🔗</tg-emoji> Рефералов: <b>{refs} · заработано {ref_earned} ₽</b>\n\n<tg-emoji emoji-id=\"5427321817134051632\">🆔</tg-emoji> Ваш ID: <b>{user_id}</b>", None),
            ("shop", "Claude AI Store\n<tg-emoji emoji-id=\"5348475279960456198\">🛍</tg-emoji> Магазин\n<b>━━━━━━━━━━━━━</b>\n\nВыберите категорию:", None),
            ("catalog", "API-ключи\n<b>━━━━━━━━━━━━━</b>\n\nВыберите товар для покупки:", None)
        ]
        for screen, text, photo in default_settings:
            await db.execute("INSERT OR IGNORE INTO settings (screen_name, text, photo_id) VALUES (?, ?, ?)", (screen, text, photo))
        
        await db.commit()

async def register_user(user_id: int, first_name: str, username: Optional[str]):
    """Регистрация или обновление данных пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, first_name, username) 
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET 
            first_name=excluded.first_name, 
            username=excluded.username
        """, (user_id, first_name, username))
        await db.commit()

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    """Получить данные пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_screen_settings(screen_name: str) -> Dict[str, Any]:
    """Получить текст и фото для экрана."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT text, photo_id FROM settings WHERE screen_name = ?", (screen_name,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else {}

async def update_screen_setting(screen_name: str, text: Optional[str] = None, photo_id: Optional[str] = None):
    """Обновить настройки экрана (используется в админке)."""
    async with aiosqlite.connect(DB_PATH) as db:
        if text is not None:
            await db.execute("UPDATE settings SET text = ? WHERE screen_name = ?", (text, screen_name))
        if photo_id is not None:
            # Если передали "0" или "none", значит нужно удалить фото
            if photo_id in ["0", "none"]:
                photo_id = None
            await db.execute("UPDATE settings SET photo_id = ? WHERE screen_name = ?", (photo_id, screen_name))
        await db.commit()

async def get_active_products() -> List[Dict[str, Any]]:
    """Получить список всех активных товаров."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE is_active = 1") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    """Получить данные товара по ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM products WHERE id = ?", (product_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_product_stock(product_id: int) -> int:
    """Узнать, сколько ключей осталось в наличии."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM product_keys WHERE product_id = ? AND is_sold = 0", (product_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def buy_product(user_id: int, product_id: int) -> Dict[str, Any]:
    """
    Атомарная покупка товара. 
    Проверяет баланс, наличие ключа, списывает деньги и выдает ключ.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Начинаем транзакцию
        await db.execute("BEGIN IMMEDIATE")
        
        try:
            # 1. Получаем пользователя
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                await db.rollback()
                return {"success": False, "error": "Пользователь не найден"}

            # 2. Получаем товар
            async with db.execute("SELECT price, is_active FROM products WHERE id = ?", (product_id,)) as cursor:
                product = await cursor.fetchone()
            if not product or not product['is_active']:
                await db.rollback()
                return {"success": False, "error": "Товар недоступен"}

            # 3. Проверяем баланс
            if user['balance'] < product['price']:
                await db.rollback()
                return {"success": False, "error": "Недостаточно средств на балансе"}

            # 4. Ищем свободный ключ
            async with db.execute("SELECT id, key_text FROM product_keys WHERE product_id = ? AND is_sold = 0 LIMIT 1", (product_id,)) as cursor:
                key_row = await cursor.fetchone()
            
            if not key_row:
                await db.rollback()
                return {"success": False, "error": "Товара нет в наличии"}

            # 5. Списываем баланс и обновляем статистику
            new_balance = user['balance'] - product['price']
            await db.execute("""
                UPDATE users 
                SET balance = ?, total_spent = total_spent + ?, purchases_count = purchases_count + 1 
                WHERE user_id = ?
            """, (new_balance, product['price'], user_id))

            # 6. Помечаем ключ как проданный
            await db.execute("""
                UPDATE product_keys 
                SET is_sold = 1, sold_to = ?, sold_date = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (user_id, key_row['id']))

            # 7. Записываем в историю заказов
            await db.execute("""
                INSERT INTO orders (user_id, product_id, key_id, price) 
                VALUES (?, ?, ?, ?)
            """, (user_id, product_id, key_row['id'], product['price']))

            await db.commit()
            return {"success": True, "key": key_row['key_text'], "balance": new_balance}

        except Exception as e:
            await db.rollback()
            print(f"DB Error in buy_product: {e}")
            return {"success": False, "error": "Ошибка базы данных при покупке"}

# ================= ФУНКЦИИ ДЛЯ АДМИНКИ =================

async def add_product(name: str, description: str, price: int) -> int:
    """Добавляет новый товар и возвращает его ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO products (name, description, price) VALUES (?, ?, ?)",
            (name, description, price)
        )
        await db.commit()
        return cursor.lastrowid

async def add_product_keys(product_id: int, keys_list: List[str]) -> int:
    """Добавляет ключи к товару. Возвращает количество добавленных."""
    async with aiosqlite.connect(DB_PATH) as db:
        for key in keys_list:
            if key.strip():
                await db.execute("INSERT INTO product_keys (product_id, key_text) VALUES (?, ?)", (product_id, key.strip()))
        await db.commit()
        return len(keys_list)

async def get_all_users_ids() -> List[int]:
    """Получить ID всех пользователей для рассылки."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE is_banned = 0") as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
