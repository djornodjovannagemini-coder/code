import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

TOKEN = os.getenv("CRYPTOPAY_TOKEN") or os.getenv("CRYPTO_BOT_TOKEN")

_client = None


def enabled() -> bool:
    """CryptoBot включается сам, как только в переменных появился токен."""
    return bool(TOKEN)


async def _get_client():
    global _client
    if _client is None:
        from aiocryptopay import AioCryptoPay, Networks
        _client = AioCryptoPay(token=TOKEN, network=Networks.MAIN_NET)
    return _client


def _status(invoice) -> str:
    status = getattr(invoice, "status", "")
    return str(getattr(status, "value", status)).lower()


async def create_invoice(amount_rub: float, payload: str, expires_in: int = 300) -> Optional[Dict[str, Any]]:
    """Счёт на amount_rub рублей (фиат). Возвращает id, ссылку и оценку в USDT."""
    if not enabled():
        return None
    try:
        client = await _get_client()
        invoice = await client.create_invoice(
            asset="USDT",
            amount=amount_rub,
            currency_type="fiat",
            fiat="RUB",
            description=f"Пополнение баланса на {amount_rub:g} ₽",
            payload=payload,
            expires_in=expires_in,
        )
        url = invoice.bot_invoice_url or getattr(invoice, "mini_app_invoice_url", None)
        usdt = None
        try:
            usdt = await client.get_amount_by_fiat(amount_rub, "USDT", "RUB")
        except Exception:
            logger.warning("CryptoBot: не удалось получить курс USDT")
        return {"id": str(invoice.invoice_id), "url": url, "usdt": usdt}
    except Exception:
        logger.exception("CryptoBot: не удалось создать счёт на %s ₽", amount_rub)
        return None


async def is_paid(invoice_id: str) -> bool:
    if not enabled() or not invoice_id:
        return False
    try:
        client = await _get_client()
        invoices = await client.get_invoices(invoice_ids=[int(invoice_id)])
        if not invoices:
            return False
        if isinstance(invoices, list):
            invoices = invoices[0]
        return _status(invoices) == "paid"
    except Exception:
        logger.exception("CryptoBot: не удалось проверить счёт %s", invoice_id)
        return False


async def delete_invoice(invoice_id: str) -> bool:
    if not enabled() or not invoice_id:
        return False
    try:
        client = await _get_client()
        return bool(await client.delete_invoice(int(invoice_id)))
    except Exception:
        logger.exception("CryptoBot: не удалось удалить счёт %s", invoice_id)
        return False


async def close():
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            logger.exception("CryptoBot: ошибка при закрытии клиента")
        _client = None
