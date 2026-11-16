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


async def create_invoice(amount_rub: int, payload: str) -> Optional[Dict[str, Any]]:
    """Счёт на amount_rub рублей. Возвращает {'id': str, 'url': str} либо None при ошибке."""
    if not enabled():
        return None
    try:
        client = await _get_client()
        invoice = await client.create_invoice(
            asset="USDT",
            amount=amount_rub,
            currency_type="fiat",
            fiat="RUB",
            description=f"Пополнение баланса на {amount_rub} ₽",
            payload=payload,
        )
        url = invoice.bot_invoice_url or getattr(invoice, "mini_app_invoice_url", None)
        return {"id": str(invoice.invoice_id), "url": url}
    except Exception:
        logger.exception("CryptoBot: не удалось создать счёт на %s ₽", amount_rub)
        return None


async def is_paid(invoice_id: str) -> bool:
    if not enabled() or not invoice_id:
        return False
    try:
        client = await _get_client()
        invoices = await client.get_invoices(invoice_ids=[int(invoice_id)])
        return bool(invoices) and _status(invoices[0]) == "paid"
    except Exception:
        logger.exception("CryptoBot: не удалось проверить счёт %s", invoice_id)
        return False


async def close():
    global _client
    if _client is not None:
        try:
            await _client.close()
        except Exception:
            logger.exception("CryptoBot: ошибка при закрытии клиента")
        _client = None
