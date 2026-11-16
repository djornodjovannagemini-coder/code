import hmac
import json
import logging
import os
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("CASHERA_BASE_URL", "https://api.cashera.cash/api/v1").rstrip("/")
API_KEY = os.getenv("CASHERA_API_KEY", "")
API_SECRET = os.getenv("CASHERA_API_SECRET", "")
CALLBACK_URL = os.getenv("CASHERA_CALLBACK_URL", "")
TIMEOUT = aiohttp.ClientTimeout(total=25)


class CasheraError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def enabled() -> bool:
    return bool(API_KEY)


def _header(headers, name: str) -> str:
    value = headers.get(name)
    if value is None:
        low = name.lower()
        for k, v in headers.items():
            if k.lower() == low:
                return v
    return value or ""


def verify_webhook(headers) -> bool:
    """Постоянное по времени сравнение заголовков вебхука (X-Api-Key + X-Secret)."""
    if not API_KEY or not API_SECRET:
        return False
    key = _header(headers, "X-Api-Key").encode("utf-8", "replace")
    secret = _header(headers, "X-Secret").encode("utf-8", "replace")
    return hmac.compare_digest(key, API_KEY.encode()) and hmac.compare_digest(secret, API_SECRET.encode())


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    return url if url.startswith(("http://", "https://")) else "https://" + url


async def _request(method: str, path: str, payload: Optional[dict] = None) -> Dict[str, Any]:
    headers = {"X-Api-Key": API_KEY, "Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    try:
        async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
            async with session.request(method, BASE_URL + path, headers=headers, json=payload) as resp:
                raw = await resp.text()
                try:
                    data = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    raise CasheraError(resp.status, f"Некорректный ответ: {raw[:200]}")
                if resp.status >= 400:
                    raise CasheraError(resp.status, data.get("message") or f"HTTP {resp.status}")
                return data
    except aiohttp.ClientError as e:
        raise CasheraError(0, f"Сетевая ошибка: {e}") from e
    except TimeoutError as e:
        raise CasheraError(0, "Таймаут запроса к Cashera") from e


async def create_payment(amount_rub: int, external_id: str, description: str,
                         method: Optional[str] = None,
                         callback_url: Optional[str] = None) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "amount": int(round(amount_rub * 100)),
        "currency": "RUB",
        "external_id": external_id,
        "description": description[:255],
        "metadata": {"external_id": external_id},
    }
    if method:
        payload["payment_method"] = method
    if callback_url or CALLBACK_URL:
        payload["callback_url"] = callback_url or CALLBACK_URL

    data = await _request("POST", "/integration/transactions", payload)
    return {
        "uuid": data.get("uuid"),
        "status": (data.get("status") or "").lower(),
        "payment_url": _normalize_url(data.get("payment_url") or ""),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
        "expires_at": data.get("expires_at"),
        "methods": [m.get("code") for m in (data.get("available_payment_methods") or [])],
        "raw": data,
    }


async def get_payment(uuid: Optional[str] = None, external_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if uuid:
        path = f"/integration/transactions/{uuid}"
    elif external_id:
        path = f"/integration/transactions/by-external-id/{external_id}"
    else:
        raise ValueError("Нужен uuid или external_id")
    try:
        data = await _request("GET", path)
    except CasheraError as e:
        if e.status == 404:
            return None
        raise
    return {
        "uuid": data.get("uuid"),
        "status": (data.get("status") or "").lower(),
        "amount": data.get("amount"),
        "currency": data.get("currency"),
        "payment_method": data.get("payment_method"),
        "paid_at": data.get("paid_at"),
        "expires_at": data.get("expires_at"),
        "raw": data,
    }


async def h2h(uuid: str) -> Optional[Dict[str, Any]]:
    """Реквизиты для своего UI: {'amount': ..., 'qr': ...}. Доступно для sbp, card, crypto."""
    try:
        return await _request("GET", f"/integration/transactions/{uuid}/h2h")
    except CasheraError as e:
        logger.warning("Cashera H2H недоступен для %s: %s", uuid, e.message)
        return None
