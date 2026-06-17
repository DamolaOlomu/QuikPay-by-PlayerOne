"""
app/integrations/glyde.py
Thin async client for Glyde's payment API.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import httpx

from app.core.config import get_settings
from app.core.exceptions import PaymentProcessorError, ValidationError


def to_minor_units(amount: Decimal) -> int:
    """Convert NGN major units to kobo for Glyde."""
    return int((amount * Decimal("100")).quantize(Decimal("1")))


class GlydeClient:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        secret_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.GLYDE_BASE_URL).rstrip("/")
        self.secret_key = secret_key if secret_key is not None else settings.GLYDE_SECRET_KEY
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.secret_key:
            raise ValidationError("GLYDE_SECRET_KEY is required when Glyde is enabled.")
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json,
                    params=params,
                )
        except httpx.HTTPError as exc:
            raise PaymentProcessorError(f"Glyde request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise PaymentProcessorError("Glyde returned a non-JSON response.") from exc

        if response.status_code >= 400:
            message = payload.get("message") or payload.get("error") or "Glyde request failed."
            raise PaymentProcessorError(message, detail=payload)

        status = str(payload.get("status", "")).lower()
        success = payload.get("success")
        if status in {"failed", "error"} or success is False:
            message = payload.get("message") or payload.get("error") or "Glyde request failed."
            raise PaymentProcessorError(message, detail=payload)

        return payload

    async def banks(self) -> dict[str, Any]:
        return await self._request("GET", "/banks")

    async def account_enquiry(self, *, account_number: str, bank_code: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "/account-enquiry",
            params={"account_number": account_number, "bank_code": bank_code},
        )

    async def balance(self) -> dict[str, Any]:
        return await self._request("GET", "/check-balance")

    async def initiate_transfer(
        self,
        *,
        amount: Decimal,
        bank_code: str,
        account_number: str,
        reference: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/transfer/initiate",
            json={
                "amount": to_minor_units(amount),
                "bank_code": bank_code,
                "account_number": account_number,
                "reference": reference,
            },
        )

    async def initialise_collection(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference: str,
        customer_name: str,
        customer_email: Optional[str],
        channels: list[str],
        default_channel: str,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/collection/initialise",
            json={
                "currency": currency.upper(),
                "amount": to_minor_units(amount),
                "reference": reference,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                },
                "channels": channels,
                "default_channel": default_channel,
            },
        )

    async def collection_bank_transfer(
        self,
        *,
        amount: Decimal,
        currency: str,
        reference: str,
        customer_name: str,
        customer_email: Optional[str],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/collection/bank-transfer",
            json={
                "currency": currency.upper(),
                "amount": to_minor_units(amount),
                "reference": reference,
                "customer_name": customer_name,
                "customer_email": customer_email,
            },
        )

    async def create_virtual_account(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", "/virtual-accounts", json=payload)

    async def fetch_transaction(self, reference: str) -> dict[str, Any]:
        return await self._request("GET", f"/transactions/{reference}")
