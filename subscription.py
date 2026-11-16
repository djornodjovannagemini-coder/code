import logging
import time
from typing import Dict, Optional, Tuple

from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)

OK_STATUSES = {"creator", "administrator", "member"}
CACHE_OK_TTL = 300
CACHE_FAIL_TTL = 30

# user_id -> (подписан, до какого момента валидно)
_cache: Dict[int, Tuple[bool, float]] = {}
_broken_reported = False


async def channel() -> str:
    import database as db
    value = (await db.get_setting("sub_channel", "@anthropc_claude")).strip()
    if value.startswith("https://t.me/"):
        value = "@" + value[len("https://t.me/"):].strip("/")
    elif value.startswith("t.me/"):
        value = "@" + value[len("t.me/"):].strip("/")
    if value and not value.startswith("@") and not value.lstrip("-").isdigit():
        value = "@" + value
    return value


async def enabled() -> bool:
    import database as db
    return await db.get_setting("sub_check", "1") == "1"


def clear_cache() -> None:
    _cache.clear()


def _status_of(member) -> str:
    status = getattr(member, "status", "")
    return str(getattr(status, "value", status)).lower()


async def _ask_telegram(bot, user_id: int) -> Tuple[bool, Optional[str]]:
    """(подписан, текст ошибки). Ошибка значит «проверить не смогли»."""
    try:
        member = await bot.get_chat_member(await channel(), user_id)
    except TelegramBadRequest as e:
        text = str(e).lower()
        if any(w in text for w in ("user not found", "participant", "member list is inaccessible")):
            # «member list is inaccessible» — бот не админ; это не вина пользователя
            if "inaccessible" in text:
                return False, str(e)
            return False, None
        return False, str(e)
    except Exception as e:  # сеть, таймаут и прочее
        logger.warning("Подписка: ошибка запроса к Telegram: %s", e)
        return False, str(e)

    status = _status_of(member)
    if status in OK_STATUSES:
        return True, None
    if status == "restricted":
        return bool(getattr(member, "is_member", False)), None
    return False, None


async def is_subscribed(bot, user_id: int, force: bool = False) -> bool:
    """True — можно пускать. При невозможности проверить пускаем (fail-open) и пишем в лог."""
    global _broken_reported
    if not force:
        cached = _cache.get(user_id)
        if cached and cached[1] > time.monotonic():
            return cached[0]

    ok, error = await _ask_telegram(bot, user_id)
    if error and not ok:
        if not _broken_reported:
            _broken_reported = True
            logger.error("Подписка: проверка невозможна (%s). Убедитесь, что бот админ канала %s",
                         error, await channel())
        _cache.pop(user_id, None)
        return True

    _cache[user_id] = (ok, time.monotonic() + (CACHE_OK_TTL if ok else CACHE_FAIL_TTL))
    return ok


async def diagnose(bot) -> Optional[str]:
    """Проверяет, может ли бот вообще читать участников канала. Возвращает текст проблемы или None."""
    ch = await channel()
    try:
        chat = await bot.get_chat(ch)
        me = await bot.get_me()
        await bot.get_chat_member(ch, me.id)
        return None if chat else f"канал {ch} не найден"
    except Exception as e:
        return f"{ch}: {e}"
