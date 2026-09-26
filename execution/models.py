"""Validated simulator boundaries and immutable request records."""

from decimal import Decimal
from typing import Annotated, ClassVar, Final, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)
from typing_extensions import Self, assert_never

PositiveQty = Annotated[int, Field(strict=True, gt=0)]
Quantity = Annotated[int, Field(strict=True, ge=0)]
Delta = Annotated[int, Field(strict=True)]
Price = Annotated[str, Field(strict=True, pattern=r"^[0-9]+(\.[0-9]+)?$")]
Key = Annotated[str, Field(strict=True, pattern=r"^[!-~]+$")]


class Boundary(BaseModel):
    """Reject unknown fields and prevent accidental mutation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class Scope(Boundary):
    """Full idempotency and ownership namespace; simulator is the only adapter."""

    broker_adapter: Literal["virtual"] = "virtual"
    account_id: Key
    environment: Literal["PAPER", "LIVE"]
    execution_scope: UUID


class Command(Boundary):
    """Fields shared by each independent trading intention."""

    key: Key
    symbol: Key
    side: Literal["BUY", "SELL"]
    config_version: PositiveQty
    expires_at: AwareDatetime | None = None


class New(Command):
    """Explicit order conditions without inferred exchange defaults."""

    kind: Literal["NEW"] = "NEW"
    qty: PositiveQty
    order_type: Literal["LIMIT", "MARKET"]
    price: Price | None = None
    session: Literal["REGULAR"]
    validity: Literal["DAY"]
    stop_latch_version: PositiveQty | None = None

    @field_validator("price")
    @classmethod
    def canonical_price(cls, value: str | None) -> str | None:
        """Canonicalize decimal strings without binary floating point."""
        if value is None:
            return None
        return (
            format(Decimal(value), "f").rstrip("0").rstrip(".")
            if "." in value
            else value.lstrip("0") or "0"
        )

    @model_validator(mode="after")
    def check_price(self) -> Self:
        """Require a positive limit price and an absent market price."""
        if self.stop_latch_version is not None and (
            self.side != "SELL" or self.order_type != "MARKET"
        ):
            raise LedgerError("STOP_LINK_REQUIRES_MARKET_SELL")
        match self.order_type:
            case "LIMIT":
                if self.price is None or Decimal(self.price) <= 0:
                    raise LedgerError("LIMIT_PRICE_REQUIRED")
            case "MARKET":
                if self.price is not None:
                    raise LedgerError("MARKET_PRICE_MUST_BE_NULL")
            case _:
                assert_never(self.order_type)
        return self


class Change(Command):
    """Versioned linkage to the exact logical order being changed."""

    target: UUID
    link_version: PositiveQty


class Amend(Change):
    """Omitted price retains the old price; increases are audited but unsupported."""

    kind: Literal["AMEND"] = "AMEND"
    qty_delta: Delta = 0
    price: Price | None = None

    @field_validator("price")
    @classmethod
    def canonical_price(cls, value: str | None) -> str | None:
        """Share exact decimal canonicalization with new orders."""
        return New.canonical_price(value)

    @model_validator(mode="after")
    def check_patch(self) -> Self:
        """Reject explicit null, zero prices and empty amendments."""
        if "price" in self.model_fields_set and (
            self.price is None or Decimal(self.price) <= 0
        ):
            raise LedgerError("AMEND_PRICE_MUST_BE_POSITIVE")
        if self.qty_delta == 0 and self.price is None:
            raise LedgerError("EMPTY_AMENDMENT")
        return self


class Cancel(Change):
    """Cancellation quantity is fixed when the intention is created."""

    kind: Literal["CANCEL"] = "CANCEL"
    cancel_qty: PositiveQty


OrderCommand = Annotated[New | Amend | Cancel, Field(discriminator="kind")]
COMMAND: Final[TypeAdapter[OrderCommand]] = TypeAdapter(OrderCommand)


class Request(Boundary):
    """Durable normalized intention, independent of transport observations."""

    request_id: UUID
    order_id: UUID
    command: OrderCommand
    decision: Literal["ACCEPTED", "REJECTED_UNSUPPORTED"]
    normalization_version: Literal[1] = 1
    digest: str


class AppliedConfig(Boundary):
    """Locally persisted configuration revision with optional desired-command proof."""

    symbol: Key
    version: PositiveQty
    command_id: UUID | None = None
    command_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    @model_validator(mode="after")
    def paired_command_proof(self) -> Self:
        """Never retain only half of the desired-command idempotency proof."""
        if (self.command_id is None) != (self.command_digest is None):
            raise ValueError("APPLIED_CONFIG_COMMAND_PROOF_INCOMPLETE")
        return self


class VirtualStopBinding(Boundary):
    """Inert, durable stop rule paired with an applied simulator revision."""

    symbol: Key
    version: PositiveQty
    rule_kind: Literal["PRICE_AT_OR_BELOW", "AVERAGE_COST_DROP"]
    threshold: Price

    @model_validator(mode="after")
    def check_threshold(self) -> Self:
        """Forbid zero and impossible percentage thresholds."""
        value = Decimal(self.threshold)
        if value <= 0 or (self.rule_kind == "AVERAGE_COST_DROP" and value >= 1):
            raise LedgerError("INVALID_STOP_THRESHOLD")
        return self


class StopRuleAssignment(Boundary):
    """Durable rule identity for a confirmed buy fill, not a sell obligation."""

    fill_event_id: UUID
    symbol: Key
    qty: PositiveQty
    rule_version: PositiveQty


class StopLatch(Boundary):
    """Durable virtual stop signal; no authorization to send an order."""

    symbol: Key
    rule_version: PositiveQty
    rule_kind: Literal["PRICE_AT_OR_BELOW", "AVERAGE_COST_DROP"]
    quote_price: Price
    quote_received_at: AwareDatetime


class StopQuoteCheckpoint(Boundary):
    """Last accepted virtual stop input for monotonic replay protection."""

    symbol: Key
    price: Price
    received_at: AwareDatetime
    evaluated_at: AwareDatetime


class StopSellObligation(Boundary):
    """One immutable protected share slice paired with one sell request."""

    request_id: UUID
    order_id: UUID
    symbol: Key
    qty: PositiveQty
    rule_version: PositiveQty


class Allocation(Boundary):
    """Explicit starting managed ownership, never inferred from a balance query."""

    symbol: Key
    qty: Quantity


class Control(Boundary):
    """Persisted entry and liquidation switches for one symbol."""

    symbol: Key
    entry_stopped: bool
    liquidating: bool


class LedgerError(ValueError):
    """Machine-readable boundary or ledger rejection."""

    def __init__(self, code: str) -> None:
        """Preserve the rejection code for callers and diagnostics."""
        self.code: str = code
        super().__init__(code)
