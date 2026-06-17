"""
app/api/v1/endpoints/webhooks.py
Inbound webhook receiver — validates HMAC signatures before processing.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import verify_webhook_signature
from app.core.logging import get_logger
from app.db.session import get_db
from app.models.transaction import Transaction

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
log = get_logger(__name__)


@router.post(
    "/payment-processor",
    status_code=status.HTTP_200_OK,
    summary="Inbound webhook from payment processor",
    description="Validates HMAC-SHA256 signature in `X-Webhook-Signature` header.",
)
async def payment_processor_webhook(
    request: Request,
    x_webhook_signature: str = Header(alias="X-Webhook-Signature"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()

    if not verify_webhook_signature(body, x_webhook_signature):
        log.warning("webhook.invalid_signature", path=str(request.url))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    event_type = payload.get("event")
    log.info("webhook.received", event_type=event_type)

    # Route to handler based on event type
    handlers = {
        "transaction.success": _handle_transaction_success,
        "transaction.failed": _handle_transaction_failed,
        "transaction.reversed": _handle_transaction_reversed,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(payload, db)
    else:
        log.warning("webhook.unhandled_event", event_type=event_type)

    return {"status": "received"}


@router.post(
    "/glyde",
    status_code=status.HTTP_200_OK,
    summary="Inbound webhook from Glyde",
    description="Validates Glyde's `X-Signature-Hash` HMAC-SHA256 header.",
)
async def glyde_webhook(
    request: Request,
    x_signature_hash: str = Header(alias="X-Signature-Hash"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    settings = get_settings()

    if settings.GLYDE_WEBHOOK_SIGNING_KEY and not verify_webhook_signature(
        body,
        x_signature_hash,
        settings.GLYDE_WEBHOOK_SIGNING_KEY,
    ):
        log.warning("glyde_webhook.invalid_signature", path=str(request.url))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature.",
        )

    try:
        payload: dict[str, Any] = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload.")

    event_type = payload.get("event")
    log.info("glyde_webhook.received", event_type=event_type)

    handlers = {
        "collection.success": _handle_glyde_success,
        "transfer.success": _handle_glyde_success,
        "transfer.successful": _handle_glyde_success,
        "transfer.failed": _handle_glyde_failed,
    }

    handler = handlers.get(event_type)
    if handler:
        await handler(payload, db)
    else:
        log.warning("glyde_webhook.unhandled_event", event_type=event_type)

    return {"status": "received"}


async def _find_transaction_for_glyde_event(payload: dict, db: AsyncSession) -> Transaction | None:
    data = payload.get("data", {})
    merchant_reference = data.get("merchant_reference")
    provider_reference = data.get("reference")
    if not merchant_reference and not provider_reference:
        return None

    result = await db.execute(
        select(Transaction).where(
            or_(
                Transaction.reference == merchant_reference,
                Transaction.external_reference == provider_reference,
            )
        )
    )
    return result.scalar_one_or_none()


async def _handle_glyde_success(payload: dict, db: AsyncSession) -> None:
    from app.models.transaction import TransactionStatus
    from app.schemas.transaction import TransactionStatusUpdate
    from app.services.transaction_service import TransactionService

    txn = await _find_transaction_for_glyde_event(payload, db)
    if not txn:
        return

    external_ref = payload.get("data", {}).get("reference")
    try:
        await TransactionService(db).update_status(
            txn.id,
            TransactionStatusUpdate(
                status=TransactionStatus.SUCCESS,
                external_reference=external_ref,
                note="Confirmed by Glyde webhook.",
            ),
            actor_id="glyde",
        )
    except Exception as exc:
        log.error("glyde_webhook.success_handler_error", txn_id=txn.id, error=str(exc))


async def _handle_glyde_failed(payload: dict, db: AsyncSession) -> None:
    from app.models.transaction import TransactionStatus
    from app.schemas.transaction import TransactionStatusUpdate
    from app.services.transaction_service import TransactionService

    txn = await _find_transaction_for_glyde_event(payload, db)
    if not txn:
        return

    try:
        await TransactionService(db).update_status(
            txn.id,
            TransactionStatusUpdate(
                status=TransactionStatus.FAILED,
                note=payload.get("data", {}).get("failure_reason", "Failed by Glyde webhook."),
            ),
            actor_id="glyde",
        )
    except Exception as exc:
        log.error("glyde_webhook.failed_handler_error", txn_id=txn.id, error=str(exc))


async def _handle_transaction_success(payload: dict, db: AsyncSession) -> None:
    from app.models.transaction import TransactionStatus
    from app.schemas.transaction import TransactionStatusUpdate
    from app.services.transaction_service import TransactionService

    txn_id = payload.get("data", {}).get("internal_reference")
    external_ref = payload.get("data", {}).get("processor_reference")
    if not txn_id:
        return

    svc = TransactionService(db)
    try:
        await svc.update_status(
            txn_id,
            TransactionStatusUpdate(
                status=TransactionStatus.SUCCESS,
                external_reference=external_ref,
                note="Confirmed by payment processor webhook.",
            ),
            actor_id="system",
        )
    except Exception as exc:
        log.error("webhook.transaction_success_handler_error", txn_id=txn_id, error=str(exc))


async def _handle_transaction_failed(payload: dict, db: AsyncSession) -> None:
    from app.models.transaction import TransactionStatus
    from app.schemas.transaction import TransactionStatusUpdate
    from app.services.transaction_service import TransactionService

    txn_id = payload.get("data", {}).get("internal_reference")
    if not txn_id:
        return

    svc = TransactionService(db)
    try:
        await svc.update_status(
            txn_id,
            TransactionStatusUpdate(
                status=TransactionStatus.FAILED,
                note=payload.get("data", {}).get("failure_reason", "Failed per processor."),
            ),
            actor_id="system",
        )
    except Exception as exc:
        log.error("webhook.transaction_failed_handler_error", txn_id=txn_id, error=str(exc))


async def _handle_transaction_reversed(payload: dict, db: AsyncSession) -> None:
    log.info("webhook.reversal_received", data=payload.get("data"))
