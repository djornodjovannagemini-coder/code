import json
import logging
import os
from typing import Awaitable, Callable, Optional

from aiohttp import web

import database as db
import payments_cashera as cashera

logger = logging.getLogger(__name__)

FAILED_STATUSES = {"canceled", "failed", "expired"}
_credit: Optional[Callable[[int], Awaitable[bool]]] = None


def configure(credit_handler: Callable[[int], Awaitable[bool]]) -> None:
    global _credit
    _credit = credit_handler


async def handle_event(payload: dict) -> None:
    """Главный обработчик платёжных событий Cashera. Идемпотентен по (uuid, status)."""
    if payload.get("event") != "transaction.status_updated":
        return

    tx = payload.get("transaction") or {}
    uuid = tx.get("uuid")
    status = (tx.get("status") or "").lower()
    if not uuid or not status:
        return

    external_id = tx.get("external_id") or ""
    dep = await db.get_deposit_by_cashera_uuid(uuid)
    if not dep and external_id.startswith("dep-"):
        try:
            dep = await db.get_deposit(int(external_id[4:]))
        except (ValueError, TypeError):
            dep = None
    if not dep:
        logger.warning("Cashera: событие для неизвестного платежа %s (%s)", uuid, external_id)
        return

    if status != "paid":
        if not await db.mark_event_once("cashera", uuid, status, json.dumps(tx, ensure_ascii=False)):
            return
        if status in FAILED_STATUSES and dep['status'] == 'pending':
            await db.cancel_deposit(dep['id'])
        return

    # paid: сверяем сумму и валюту с заявкой, прежде чем что-то зачислять
    amount = tx.get("amount")
    if amount is not None and int(amount) != int(dep['amount']) * 100:
        logger.error("Cashera: сумма %s не совпала с заявкой #%s (%s коп.)",
                     amount, dep['id'], int(dep['amount']) * 100)
        await db.mark_event_once("cashera", uuid, status, json.dumps(tx, ensure_ascii=False))
        return
    if (tx.get("currency") or "RUB").upper() != "RUB":
        logger.error("Cashera: неожиданная валюта %s для заявки #%s", tx.get("currency"), dep['id'])
        await db.mark_event_once("cashera", uuid, status, json.dumps(tx, ensure_ascii=False))
        return

    if _credit is None:
        logger.error("Cashera: обработчик зачисления не настроен, событие будет повторено")
        raise RuntimeError("credit handler is not configured")

    await _credit(dep['id'])
    await db.mark_event_once("cashera", uuid, status, json.dumps(tx, ensure_ascii=False))
    logger.info("Cashera: заявка #%s зачислена по вебхуку (%s)", dep['id'], uuid)


async def _health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "cashera": cashera.enabled()})


async def _cashera_webhook(request: web.Request) -> web.Response:
    if not cashera.enabled():
        return web.json_response({"message": "cashera disabled"}, status=503)
    if not cashera.verify_webhook(request.headers):
        logger.warning("Cashera: вебхук отклонён — неверные X-Api-Key/X-Secret")
        return web.json_response({"message": "unauthorized"}, status=401)
    try:
        payload = json.loads(await request.text() or "{}")
    except json.JSONDecodeError:
        return web.json_response({"message": "bad json"}, status=400)
    try:
        await handle_event(payload)
    except Exception:
        logger.exception("Cashera: ошибка обработки вебхука, просим повторить")
        return web.json_response({"message": "retry later"}, status=500)
    return web.json_response({"ok": True})


async def start_server(credit_handler, port: int = None) -> Optional[web.AppRunner]:
    configure(credit_handler)
    port = port or int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", _health)
    app.router.add_get("/health", _health)
    app.router.add_post("/webhooks/cashera", _cashera_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()
    logger.info("HTTP-сервер слушает порт %s, вебхук: /webhooks/cashera", port)
    return runner


async def stop_server(runner: Optional[web.AppRunner]) -> None:
    if runner is not None:
        await runner.cleanup()
