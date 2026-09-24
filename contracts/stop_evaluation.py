"""Pure stop observation: never submits an order or invents a quote."""

from datetime import timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator
from typing_extensions import Self

from contracts.settings import Contract, StopRule


class ManagedPosition(Contract):
    """Confirmed managed shares and their confirmed cost basis."""

    symbol: Annotated[str, Field(pattern=r"^[0-9]{6}$")]
    confirmed_qty: Annotated[int, Field(strict=True, ge=0)]
    average_cost: Annotated[Decimal, Field(gt=0)]

    @field_validator("average_cost", mode="before")
    @classmethod
    def exact_cost(cls, value: object) -> object:
        """Require an exact decimal string from confirmed execution facts."""
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("DECIMAL_STRING_REQUIRED")
        return value

    @model_validator(mode="after")
    def finite_cost(self) -> Self:
        """Reject NaN and infinity before comparing a stop threshold."""
        if not self.average_cost.is_finite():
            raise ValueError("INVALID_AVERAGE_COST")
        return self


class Quote(Contract):
    """A received last trade with source timestamp; not a synthesized price."""

    symbol: Annotated[str, Field(pattern=r"^[0-9]{6}$")]
    source: Literal["LAST_TRADE"] = "LAST_TRADE"
    price: Annotated[Decimal, Field(gt=0)]
    received_at: AwareDatetime

    @field_validator("price", mode="before")
    @classmethod
    def exact_price(cls, value: object) -> object:
        """Reject approximate floating point prices at quote ingress."""
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("DECIMAL_STRING_REQUIRED")
        return value

    @model_validator(mode="after")
    def finite_price(self) -> Self:
        """Reject NaN and infinity rather than producing an ambiguous result."""
        if not self.price.is_finite():
            raise ValueError("INVALID_QUOTE_PRICE")
        return self


class ConfirmedBuyFill(Contract):
    """Price evidence for a confirmed buy fill, excluding transaction fees."""

    qty: Annotated[int, Field(strict=True, gt=0)]
    price: Annotated[Decimal, Field(gt=0)]

    @field_validator("price", mode="before")
    @classmethod
    def exact_price(cls, value: object) -> object:
        """Preserve exact prices without converting binary floats."""
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("DECIMAL_STRING_REQUIRED")
        return value

    @model_validator(mode="after")
    def finite_price(self) -> Self:
        """Reject non-finite prices before calculating the cost basis."""
        if not self.price.is_finite():
            raise ValueError("INVALID_FILL_PRICE")
        return self


def average_buy_cost(fills: tuple[ConfirmedBuyFill, ...]) -> Decimal:
    """Calculate a confirmed quantity-weighted average without fees."""
    if not fills:
        raise ValueError("CONFIRMED_BUY_FILLS_REQUIRED")
    return sum((fill.price * fill.qty for fill in fills), Decimal(0)) / sum(
        fill.qty for fill in fills
    )


class StopObservation(Contract):
    """Condition evidence only; order policy and reservation are separate."""

    status: Literal["TRIGGERED", "NOT_TRIGGERED", "UNAVAILABLE"]
    reason: str
    threshold_price: Decimal | None = None


class ProtectionExposure(Contract):
    """Confirmed virtual ledger quantities and unresolved sell evidence."""

    managed_qty: Annotated[int, Field(strict=True, ge=0)]
    reserved_sell_qty: Annotated[int, Field(strict=True, ge=0)]
    reconciliation_required: bool
    sell_uncertain: bool


class ProtectionDecision(Contract):
    """Candidate unreserved shares; never an order or a send permission."""

    status: Literal["CANDIDATE", "BLOCKED", "NONE"]
    reason: str
    unreserved_qty: int = 0


def protection_candidate(
    observation: StopObservation,
    position: ManagedPosition,
    exposure: ProtectionExposure,
) -> ProtectionDecision:
    """Avoid duplicate sell candidates while evidence or ownership is unsafe."""
    if observation.status != "TRIGGERED":
        return ProtectionDecision(status="NONE", reason=observation.reason)
    if exposure.managed_qty != position.confirmed_qty:
        return ProtectionDecision(status="BLOCKED", reason="POSITION_EVIDENCE_MISMATCH")
    if exposure.reconciliation_required or exposure.sell_uncertain:
        return ProtectionDecision(status="BLOCKED", reason="SELL_EVIDENCE_UNRESOLVED")
    if exposure.reserved_sell_qty > exposure.managed_qty:
        return ProtectionDecision(
            status="BLOCKED", reason="SELL_RESERVATION_EXCEEDS_HOLDING"
        )
    available = exposure.managed_qty - exposure.reserved_sell_qty
    if available == 0:
        return ProtectionDecision(
            status="NONE", reason="SHARES_ALREADY_RESERVED_OR_SOLD"
        )
    return ProtectionDecision(
        status="CANDIDATE",
        reason="TRIGGERED_UNRESERVED_SHARES",
        unreserved_qty=available,
    )


class ObserveAt(Contract):
    """Explicit evaluation timing supplied by the trusted local engine."""

    now: AwareDatetime
    max_quote_age_seconds: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def valid_utc_offset(self) -> Self:
        """Ensure the observation clock has an actual timezone offset."""
        if self.now.utcoffset() is None:
            raise ValueError("CLOCK_TIMEZONE_REQUIRED")
        return self


def evaluate_stop(
    position: ManagedPosition,
    quote: Quote | None,
    rule: StopRule,
    timing: ObserveAt,
) -> StopObservation:
    """Compare confirmed shares against an explicitly fresh matching quote."""
    if position.confirmed_qty == 0:
        return StopObservation(status="UNAVAILABLE", reason="NO_MANAGED_POSITION")
    if quote is None or quote.symbol != position.symbol:
        return StopObservation(
            status="UNAVAILABLE", reason="QUOTE_MISSING_OR_WRONG_SYMBOL"
        )
    age = timing.now - quote.received_at
    if age < timedelta(0) or age > timedelta(seconds=timing.max_quote_age_seconds):
        return StopObservation(status="UNAVAILABLE", reason="QUOTE_NOT_FRESH")
    threshold = (
        rule.threshold
        if rule.kind == "PRICE_AT_OR_BELOW"
        else position.average_cost * (Decimal(1) - rule.threshold)
    )
    return StopObservation(
        status="TRIGGERED" if quote.price <= threshold else "NOT_TRIGGERED",
        reason="PRICE_AT_OR_BELOW_THRESHOLD"
        if quote.price <= threshold
        else "ABOVE_THRESHOLD",
        threshold_price=threshold,
    )
