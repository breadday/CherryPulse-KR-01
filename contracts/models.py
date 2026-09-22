"""Shared API contract models for Python and TypeScript fixtures."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated, ClassVar, Literal
from uuid import UUID  # Pydantic resolves this type at runtime.

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)
from typing_extensions import Self

MAX_SAFE_INTEGER = 9_007_199_254_740_991


def _validate_schema_version(value: object) -> int:
    """Accept JSON numeric one while rejecting booleans and other primitives."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != 1:
        raise ValueError("INVALID_SCHEMA_VERSION")
    return 1


SchemaVersion = Annotated[
    int, BeforeValidator(_validate_schema_version), Field(strict=True)
]


def _validate_safe_integer(value: object, *, minimum: int) -> int:
    """Mirror JavaScript Number.isSafeInteger for decoded JSON numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("INVALID_SAFE_INTEGER")  # noqa: TRY004  # Pydantic validator.
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("INVALID_SAFE_INTEGER")
    integer = int(value)
    if integer < minimum or integer > MAX_SAFE_INTEGER:
        raise ValueError("INVALID_SAFE_INTEGER")
    return integer


def _validate_positive_integer(value: object) -> int:
    """Accept positive integral JSON numbers within JavaScript's safe range."""
    return _validate_safe_integer(value, minimum=1)


def _validate_nonnegative_integer(value: object) -> int:
    """Accept nonnegative integral JSON numbers within JavaScript's safe range."""
    return _validate_safe_integer(value, minimum=0)


PositiveInt = Annotated[
    int, BeforeValidator(_validate_positive_integer), Field(strict=True)
]
NonNegativeInt = Annotated[
    int,
    BeforeValidator(_validate_nonnegative_integer),
    Field(strict=True),
]
Symbol = Annotated[str, Field(strict=True, pattern=r"^[0-9]{6}$")]
Key = Annotated[str, Field(strict=True, pattern=r"^[!-~]+$")]
NonEmptyText = Annotated[str, Field(strict=True, min_length=1)]
DecimalText = Annotated[
    str,
    Field(strict=True, pattern=r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
]
UUID_TEXT_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
DATETIME_TEXT_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}:\d{2})$"
)


def _validate_uuid_format(value: object) -> object:
    """Require the same hyphenated UUID text accepted by the web contract."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str) or UUID_TEXT_PATTERN.fullmatch(value) is None:
        raise ValueError("INVALID_UUID_FORMAT")
    return value


ContractUuid = Annotated[UUID, BeforeValidator(_validate_uuid_format)]


def _validate_datetime_format(value: object) -> object:
    """Require the same timezone-aware datetime text accepted by the web contract."""
    if not isinstance(value, str):
        raise ValueError("INVALID_DATETIME_FORMAT")  # noqa: TRY004  # Pydantic validator.
    match = DATETIME_TEXT_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("INVALID_DATETIME_FORMAT")
    date_time, fraction, timezone = match.groups()
    normalized_fraction = "" if fraction is None else f".{fraction.ljust(3, '0')}"
    normalized = f"{date_time}{normalized_fraction}{timezone}"
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("INVALID_DATETIME_FORMAT") from error
    return value


ContractDatetime = Annotated[AwareDatetime, BeforeValidator(_validate_datetime_format)]


def canonical_decimal(value: str) -> str:
    """Return a plain decimal string without insignificant trailing zeroes."""
    normalized = format(Decimal(value), "f")
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    return "0" if normalized in {"-0", ""} else normalized


class Boundary(BaseModel):
    """Reject unknown fields and prevent accidental contract mutation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class Instrument(Boundary):
    """Korean exchange instrument displayed and executed by the product."""

    symbol: Symbol
    name: NonEmptyText
    market: Literal["KOSPI", "KOSDAQ"]


class PriceThreshold(Boundary):
    """Absolute price trigger with an explicit comparison direction."""

    kind: Literal["PRICE_THRESHOLD"] = "PRICE_THRESHOLD"
    comparison: Literal["GTE", "LTE"]
    threshold_price: DecimalText

    @field_validator("threshold_price")
    @classmethod
    def validate_price(cls, value: str) -> str:
        """Require a positive canonical price."""
        canonical = canonical_decimal(value)
        if Decimal(canonical) <= 0:
            raise ValueError("PATTERN_PRICE_MUST_BE_POSITIVE")
        return canonical


class AveragePricePercent(Boundary):
    """Loss threshold relative to the confirmed average fill price."""

    kind: Literal["AVERAGE_PRICE_PERCENT"] = "AVERAGE_PRICE_PERCENT"
    percent: DecimalText

    @field_validator("percent")
    @classmethod
    def validate_percent(cls, value: str) -> str:
        """Allow only a negative percentage strictly above -100%."""
        canonical = canonical_decimal(value)
        numeric = Decimal(canonical)
        if not Decimal(-100) < numeric < 0:
            raise ValueError("PATTERN_PERCENT_OUT_OF_RANGE")
        return canonical


PatternDefinition = Annotated[
    PriceThreshold | AveragePricePercent,
    Field(discriminator="kind"),
]


class PatternVersion(Boundary):
    """Immutable versioned condition referenced by an execution config."""

    pattern_id: ContractUuid
    version: PositiveInt
    side: Literal["BUY", "SELL"]
    name: NonEmptyText
    definition: PatternDefinition


class PatternRef(Boundary):
    """Stable reference to one immutable pattern version."""

    pattern_id: ContractUuid
    version: PositiveInt


class ExecutionConfig(Boundary):
    """Requested and applied execution configuration state."""

    execution_id: ContractUuid
    account_id: Key
    environment: Literal["PAPER", "LIVE"]
    symbol: Symbol
    buy_pattern: PatternRef
    sell_pattern: PatternRef
    requested_version: PositiveInt
    applied_version: PositiveInt | None
    state: Literal["PENDING", "ACCEPTED", "REJECTED", "EXPIRED"]
    requested_at: ContractDatetime
    expires_at: ContractDatetime
    rejection_reason: NonEmptyText | None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        """Keep request, acceptance, rejection and expiry facts unambiguous."""
        if self.expires_at <= self.requested_at:
            raise ValueError("CONFIG_EXPIRY_MUST_FOLLOW_REQUEST")
        _validate_config_result(self)
        return self


class OrderSnapshot(Boundary):
    """Read model for one logical order and its conserved quantities."""

    client_order_id: ContractUuid
    request_id: ContractUuid
    execution_id: ContractUuid
    broker_order_no: Key | None
    symbol: Symbol
    side: Literal["BUY", "SELL"]
    order_type: Literal["LIMIT", "MARKET"]
    price: DecimalText | None
    quantity: PositiveInt
    filled_quantity: NonNegativeInt
    cancelled_quantity: NonNegativeInt
    remaining_quantity: NonNegativeInt
    state: Literal[
        "PENDING",
        "OPEN",
        "PARTIALLY_FILLED",
        "FILLED",
        "CANCELLED",
        "REJECTED",
    ]

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: str | None) -> str | None:
        """Canonicalize an optional positive order price."""
        if value is None:
            return None
        canonical = canonical_decimal(value)
        if Decimal(canonical) <= 0:
            raise ValueError("ORDER_PRICE_MUST_BE_POSITIVE")
        return canonical

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        """Validate price rules, quantity conservation and lifecycle state."""
        _validate_order_price(self)
        _validate_order_quantity(self)
        _validate_order_lifecycle(self)
        return self


class FillSnapshot(Boundary):
    """Confirmed fill linked to one logical order."""

    fill_id: ContractUuid
    client_order_id: ContractUuid
    quantity: PositiveInt
    price: DecimalText
    filled_at: ContractDatetime

    @field_validator("price")
    @classmethod
    def validate_price(cls, value: str) -> str:
        """Require a positive canonical fill price."""
        canonical = canonical_decimal(value)
        if Decimal(canonical) <= 0:
            raise ValueError("FILL_PRICE_MUST_BE_POSITIVE")
        return canonical


class OperationStatus(Boundary):
    """Engine, data and reconciliation state displayed by the web board."""

    engine: Literal["ONLINE", "OFFLINE", "DEGRADED"]
    live_trading_enabled: StrictBool
    data_mode: Literal["MOCK", "PAPER", "LIVE"]
    reconciliation: Literal["OK", "RECONCILING", "RECONCILIATION_REQUIRED"]
    last_event_at: ContractDatetime | None

    @model_validator(mode="after")
    def validate_live_mode(self) -> Self:
        """Never label an offline or non-live session as live-order enabled."""
        if self.live_trading_enabled and (
            self.engine != "ONLINE" or self.data_mode != "LIVE"
        ):
            raise ValueError("LIVE_TRADING_STATUS_INVALID")
        return self


class ContractBundle(Boundary):
    """Single fixture proving the shared API boundary across runtimes."""

    schema_version: SchemaVersion
    instrument: Instrument
    patterns: tuple[PatternVersion, ...]
    execution_config: ExecutionConfig
    order: OrderSnapshot
    fills: tuple[FillSnapshot, ...]
    operation: OperationStatus

    @model_validator(mode="after")
    def validate_links(self) -> Self:
        """Validate cross-object identity, pattern and fill relationships."""
        _validate_bundle_identity(self)
        _validate_bundle_patterns(self)
        _validate_bundle_fills(self)
        return self


def _validate_config_result(config: ExecutionConfig) -> None:
    """Validate the result fields for one configuration state."""
    if config.state == "PENDING":
        if config.applied_version is not None or config.rejection_reason is not None:
            raise ValueError("PENDING_CONFIG_HAS_RESULT")
        return
    if config.state == "ACCEPTED":
        if config.applied_version != config.requested_version:
            raise ValueError("ACCEPTED_VERSION_MISMATCH")
        if config.rejection_reason is not None:
            raise ValueError("ACCEPTED_CONFIG_HAS_REJECTION")
        return
    if config.state == "REJECTED":
        if config.applied_version is not None or config.rejection_reason is None:
            raise ValueError("REJECTED_CONFIG_RESULT_INVALID")
        return
    if config.applied_version is not None or config.rejection_reason is not None:
        raise ValueError("EXPIRED_CONFIG_HAS_RESULT")


def _validate_order_price(order: OrderSnapshot) -> None:
    """Validate market and limit price presence."""
    if order.order_type == "LIMIT" and order.price is None:
        raise ValueError("LIMIT_PRICE_REQUIRED")
    if order.order_type == "MARKET" and order.price is not None:
        raise ValueError("MARKET_PRICE_MUST_BE_NULL")


def _validate_order_quantity(order: OrderSnapshot) -> None:
    """Validate rejected and conserved order quantities."""
    observed = (
        order.filled_quantity,
        order.cancelled_quantity,
        order.remaining_quantity,
    )
    if order.state == "REJECTED":
        if any(observed):
            raise ValueError("REJECTED_ORDER_HAS_QUANTITY")
        return
    if order.quantity != sum(observed):
        raise ValueError("ORDER_QUANTITY_MISMATCH")


def _validate_order_lifecycle(order: OrderSnapshot) -> None:
    """Validate quantities required by each order lifecycle state."""
    if order.state in {"PENDING", "OPEN"}:
        if order.filled_quantity or order.cancelled_quantity:
            raise ValueError("OPEN_ORDER_HAS_TERMINAL_QUANTITY")
        return
    if order.state == "PARTIALLY_FILLED":
        if order.filled_quantity <= 0 or order.remaining_quantity <= 0:
            raise ValueError("PARTIAL_ORDER_QUANTITY_INVALID")
        return
    if order.state == "FILLED":
        if (
            order.filled_quantity != order.quantity
            or order.cancelled_quantity
            or order.remaining_quantity
        ):
            raise ValueError("FILLED_ORDER_QUANTITY_INVALID")
        return
    if order.state == "CANCELLED" and (
        order.cancelled_quantity <= 0 or order.remaining_quantity
    ):
        raise ValueError("CANCELLED_ORDER_QUANTITY_INVALID")


def _validate_bundle_identity(bundle: ContractBundle) -> None:
    """Validate symbol and execution identity across the bundle."""
    if bundle.execution_config.symbol != bundle.instrument.symbol:
        raise ValueError("CONFIG_INSTRUMENT_MISMATCH")
    if (
        bundle.order.symbol != bundle.instrument.symbol
        or bundle.order.execution_id != bundle.execution_config.execution_id
    ):
        raise ValueError("ORDER_EXECUTION_MISMATCH")


def _validate_bundle_patterns(bundle: ContractBundle) -> None:
    """Validate unique pattern versions and side-specific references."""
    patterns: dict[tuple[UUID, int], PatternVersion] = {}
    for pattern in bundle.patterns:
        key = (pattern.pattern_id, pattern.version)
        if key in patterns:
            raise ValueError("DUPLICATE_PATTERN_VERSION")
        patterns[key] = pattern

    references = (
        (bundle.execution_config.buy_pattern, "BUY"),
        (bundle.execution_config.sell_pattern, "SELL"),
    )
    for reference, expected_side in references:
        pattern = patterns.get((reference.pattern_id, reference.version))
        if pattern is None:
            raise ValueError("PATTERN_REFERENCE_NOT_FOUND")
        if pattern.side != expected_side:
            raise ValueError("PATTERN_SIDE_MISMATCH")


def _validate_bundle_fills(bundle: ContractBundle) -> None:
    """Validate fill uniqueness, linkage and aggregate quantity."""
    fill_ids: set[UUID] = set()
    total_filled = 0
    for fill in bundle.fills:
        if fill.fill_id in fill_ids:
            raise ValueError("DUPLICATE_FILL")
        fill_ids.add(fill.fill_id)
        if fill.client_order_id != bundle.order.client_order_id:
            raise ValueError("FILL_ORDER_MISMATCH")
        total_filled += fill.quantity
    if total_filled != bundle.order.filled_quantity:
        raise ValueError("FILL_TOTAL_MISMATCH")
