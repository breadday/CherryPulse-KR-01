"""Inactive pattern definitions and pure configuration-command decisions.

The transport adapter must authenticate the sender before constructing Actor.
This module never submits an order or activates the virtual ledger's version.
"""

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from typing_extensions import Self


class Contract(BaseModel):
    """Forbid unrecognized fields and implicit mutation of accepted settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


class StopRule(Contract):
    """A quoted stop threshold; executable market policy remains unresolved."""

    kind: Literal["PRICE_AT_OR_BELOW", "AVERAGE_COST_DROP"]
    threshold: Annotated[Decimal, Field(gt=0)]

    @field_validator("threshold", mode="before")
    @classmethod
    def decimal_string_only(cls, value: object) -> object:
        """Reject binary floating point inputs at the configuration boundary."""
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError("DECIMAL_STRING_REQUIRED")
        return value

    @model_validator(mode="after")
    def check_threshold(self) -> Self:
        """Reject non-finite values and a drop of at least the full cost."""
        if not self.threshold.is_finite() or (
            self.kind == "AVERAGE_COST_DROP" and self.threshold >= 1
        ):
            raise ValueError("INVALID_STOP_THRESHOLD")
        return self


class Pattern(Contract):
    """Immutable rule revision, with no default order action."""

    pattern_id: UUID
    version: Annotated[int, Field(strict=True, gt=0)]
    name: Annotated[str, Field(min_length=1, max_length=100)]
    side: Literal["SELL"]
    stop: StopRule


class Settings(Contract):
    """Desired settings do not claim engine acceptance or live execution."""

    account_id: Annotated[str, Field(min_length=1)]
    environment: Literal["PAPER", "LIVE"]
    symbol: Annotated[str, Field(pattern=r"^[0-9]{6}$")]
    version: Annotated[int, Field(strict=True, gt=0)]
    stop_pattern: Pattern
    stop_order_type: Literal["MARKET", "LIMIT"] | None = None
    entry_enabled: bool = False
    monitoring_enabled: bool = False

    @model_validator(mode="after")
    def forbid_activation(self) -> Self:
        """Keep unreviewed trigger timing and order policy disabled."""
        if self.entry_enabled or self.monitoring_enabled:
            raise ValueError("PATTERN_EXECUTION_NOT_SPECIFIED")
        return self


class Actor(Contract):
    """Claims already authenticated by an external trusted ingress."""

    actor_id: Annotated[str, Field(min_length=1)]
    account_id: Annotated[str, Field(min_length=1)]
    environment: Literal["PAPER", "LIVE"]
    permissions: frozenset[Literal["CONFIG_WRITE"]]


class ConfigCommand(Contract):
    """An immutable desired-settings request, never a broker instruction."""

    command_id: UUID
    idempotency_key: Annotated[str, Field(min_length=1)]
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    expires_at: AwareDatetime
    settings: Settings


class Decision(Contract):
    """A pure result; the caller must persist it before acknowledging it."""

    state: Literal["ACCEPTED", "REJECTED"]
    reason: str
    digest: str


def digest(command: ConfigCommand) -> str:
    """Use canonical JSON for exact replay comparison within one scope."""
    return sha256(command.model_dump_json().encode("utf-8")).hexdigest()


def decide(
    command: ConfigCommand,
    actor: Actor,
    *,
    current_version: int,
    now: datetime,
) -> Decision:
    """Check scope, permission, deadline and monotonic version without I/O."""
    fingerprint = digest(command)
    reason = "ACCEPTED"
    if now.utcoffset() is None:
        reason = "CLOCK_TIMEZONE_REQUIRED"
    elif (
        actor.account_id != command.settings.account_id
        or actor.environment != command.settings.environment
        or "CONFIG_WRITE" not in actor.permissions
    ):
        reason = "CONFIG_UNAUTHORIZED"
    elif now >= command.expires_at:
        reason = "COMMAND_EXPIRED"
    elif current_version != command.expected_version:
        reason = "STALE_CONFIG_VERSION"
    elif command.settings.version <= current_version:
        reason = "CONFIG_VERSION_MUST_ADVANCE"
    return Decision(
        state="ACCEPTED" if reason == "ACCEPTED" else "REJECTED",
        reason=reason,
        digest=fingerprint,
    )
