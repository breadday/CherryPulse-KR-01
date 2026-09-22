"""Normalized virtual evidence; no claim about real brokerage event semantics."""

from decimal import Decimal
from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import Field, TypeAdapter, model_validator
from typing_extensions import Self

from execution.models import (
    Boundary,
    Delta,
    Key,
    LedgerError,
    PositiveQty,
    Price,
    Quantity,
)
from execution.query_evidence import QueryEvidence


class Evidence(Boundary):
    """Caller supplies a stable event identity within the ledger scope."""

    event_id: UUID


class Ack(Evidence):
    """A request was accepted, without asserting its business effect."""

    kind: Literal["ACK"] = "ACK"
    request_id: UUID
    broker_order_no: Key


class Observation(Evidence):
    """Simulator causal version, explicitly not a broker sequence assumption."""

    order_id: UUID
    evidence_version: PositiveQty
    remaining: Quantity


class Fill(Observation):
    """Unique execution fact, correlated to an exact logical order."""

    kind: Literal["FILL"] = "FILL"
    qty: PositiveQty


class StopLossTriggered(Evidence):
    """Confirmed virtual stop-loss evaluation that activates liquidation."""

    kind: Literal["STOP_LOSS_TRIGGERED"] = "STOP_LOSS_TRIGGERED"
    symbol: Key
    config_version: PositiveQty
    observed_price: Price
    threshold_price: Price

    @model_validator(mode="after")
    def validate_trigger(self) -> Self:
        """Require a positive observed price at or below the configured threshold."""
        observed = Decimal(self.observed_price)
        threshold = Decimal(self.threshold_price)
        if observed <= 0 or threshold <= 0:
            raise LedgerError("STOP_LOSS_PRICE_MUST_BE_POSITIVE")
        if observed > threshold:
            raise LedgerError("STOP_LOSS_NOT_TRIGGERED")
        return self


class Amended(Observation):
    """Confirmed amendment effect; quantity reduction is not cancellation."""

    kind: Literal["AMENDED"] = "AMENDED"
    request_id: UUID
    qty_delta: Delta


class Cancelled(Observation):
    """Confirmed actual cancelled quantity, which may differ from the request."""

    kind: Literal["CANCELLED"] = "CANCELLED"
    request_id: UUID
    qty: PositiveQty


class Transport(Evidence):
    """Local send boundary and uncertainty evidence."""

    kind: Literal["TRANSPORT"] = "TRANSPORT"
    request_id: UUID
    state: Literal["SENDING", "SENT", "UNKNOWN", "RECONCILING"]


class Discrepancy(Evidence):
    """Unexplained account evidence cannot create synthetic fills."""

    kind: Literal["DISCREPANCY"] = "DISCREPANCY"
    symbol: Key
    reason: Key


class Reconciled(Evidence):
    """Trusted complete virtual review of one specific discrepancy."""

    kind: Literal["RECONCILED"] = "RECONCILED"
    discrepancy_id: UUID
    symbol: Key
    observed_managed: Quantity
    reviewed_revision: Quantity
    proof_reference: Key
    source: Literal["VIRTUAL_COMPLETE_REVIEW"]
    query: QueryEvidence


class QuarantinedFill(Evidence):
    """Normalized virtual source fields awaiting exact broker-order linkage."""

    kind: Literal["QUARANTINED_FILL"] = "QUARANTINED_FILL"
    broker_order_no: Key
    symbol: Key
    qty: PositiveQty
    remaining: Quantity
    evidence_version: PositiveQty
    source: Literal["VIRTUAL"]


class QuarantineReleased(Evidence):
    """Audit linkage to the exact fill committed with a quarantine release."""

    kind: Literal["QUARANTINE_RELEASED"] = "QUARANTINE_RELEASED"
    quarantine_id: UUID
    fill_id: UUID
    proof_reference: Key


class SendFailed(Evidence):
    """A trusted local adapter proves that a specific request was never sent."""

    kind: Literal["SEND_FAILED"] = "SEND_FAILED"
    request_id: UUID
    proof: Literal["NOT_INVOKED", "VERIFIED_UNSENT"]
    reason: Key


class Rejected(Evidence):
    """An exactly correlated request rejection, not an inferred missing order."""

    kind: Literal["REJECTED"] = "REJECTED"
    request_id: UUID
    reason: Key


class EffectRejected(Evidence):
    """Accepted amendment or cancellation whose requested effect was rejected."""

    kind: Literal["EFFECT_REJECTED"] = "EFFECT_REJECTED"
    request_id: UUID
    reason: Key


Fact = Annotated[
    Ack
    | Fill
    | StopLossTriggered
    | Amended
    | Cancelled
    | Transport
    | Discrepancy
    | Reconciled
    | QuarantinedFill
    | QuarantineReleased
    | SendFailed
    | Rejected
    | EffectRejected,
    Field(discriminator="kind"),
]
FACT: Final[TypeAdapter[Fact]] = TypeAdapter(Fact)
