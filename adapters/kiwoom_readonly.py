"""Read-only Kiwoom OpenAPI+ query boundary.

This module deliberately has no order methods and never imports ``execution``.
It records raw query evidence separately; callers must not treat a normalized
snapshot as managed ownership or a fill fact without an explicit review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Protocol
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from collections.abc import Mapping


class QueryStatus(str, Enum):
    """Evidence state of a read-only query."""

    COMPLETE = "COMPLETE"
    UNKNOWN = "UNKNOWN"
    QUARANTINED = "QUARANTINED"


class ReadOnlyQueryError(ValueError):
    """The requested operation is outside the read-only boundary."""


class ControlProtocol(Protocol):
    """Small subset of QAxWidget used by this adapter."""

    def dynamicCall(self, signature: str, *args: object) -> object:  # noqa: N802
        """Invoke one explicitly read-only OpenAPI+ method."""


@dataclass(frozen=True, slots=True)
class QuerySpec:
    """A whitelisted TR request with non-secret input aliases."""

    tr_code: str
    rq_name: str
    input_values: Mapping[str, str]
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject non-whitelisted TRs and empty query inputs."""
        if self.tr_code not in READ_ONLY_TRS:
            raise ReadOnlyQueryError("TR_NOT_READ_ONLY")
        if any(not key or not value for key, value in self.input_values.items()):
            raise ReadOnlyQueryError("QUERY_INPUT_INVALID")


@dataclass(frozen=True, slots=True)
class QueryPage:
    """One response page, retaining its raw rows and continuation marker."""

    page_number: int
    prev_next: str
    received_at: datetime
    raw_rows: tuple[Mapping[str, str], ...] = ()
    raw_payload: str = ""
    finished: bool = False
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class QueryCapture:
    """Durable-shaped evidence without account secrets or ledger mutation."""

    capture_id: UUID
    account_alias: str
    environment: str
    spec: QuerySpec
    started_at: datetime
    finished_at: datetime | None
    pages: tuple[QueryPage, ...] = ()
    raw_events: tuple[Mapping[str, str], ...] = ()

    @property
    def status(self) -> QueryStatus:
        """Classify completeness; never infer success from an empty response."""
        if not self.pages or self.finished_at is None:
            return QueryStatus.UNKNOWN
        if not _capture_times_are_consistent(self):
            return QueryStatus.QUARANTINED
        numbers = tuple(page.page_number for page in self.pages)
        expected = tuple(range(1, max(numbers) + 1))
        if numbers != expected or any(
            page.error_code or not page.finished for page in self.pages
        ):
            return QueryStatus.QUARANTINED
        if not pagination_complete(tuple(page.prev_next for page in self.pages)):
            return QueryStatus.QUARANTINED
        return QueryStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class ReadOnlySnapshot:
    """Normalized display data, explicitly separated from execution facts."""

    capture_id: UUID
    status: QueryStatus
    rows: tuple[Mapping[str, str], ...]
    reason: str


@dataclass(frozen=True, slots=True)
class LoginObservation:
    """A connection-state observation, not a login success assertion."""

    connected: bool
    observed_at: datetime
    raw_state: int


# opw00007 remains blocked until its output and pagination contract is verified.
READ_ONLY_TRS: Final[frozenset[str]] = frozenset({"opw00018", "opt10075"})
EVENT_IDENTITY_FIELDS: Final[int] = 3
SENSITIVE_INPUT_NAMES: Final[frozenset[str]] = frozenset(
    {"계좌번호", "비밀번호", "비밀번호입력매체구분"}
)

POSITIONS_FIELDS: Final[tuple[str, ...]] = (
    "종목번호",
    "종목명",
    "보유수량",
    "매매가능수량",
    "매입가",
    "현재가",
)
UNFILLED_FIELDS: Final[tuple[str, ...]] = (
    "주문번호",
    "종목코드",
    "종목명",
    "주문구분",
    "주문가격",
    "주문수량",
    "미체결수량",
    "체결량",
    "주문상태",
)


def pagination_complete(markers: tuple[str, ...]) -> bool:
    """Accept continuation pages followed by exactly one terminal page."""
    return (
        bool(markers)
        and all(marker == "2" for marker in markers[:-1])
        and (markers[-1] in {"", "0"})
    )


def _capture_times_are_consistent(capture: QueryCapture) -> bool:
    """Require aware, ordered timestamps bounded by the query interval."""
    finished_at = capture.finished_at
    if finished_at is None:
        return False
    times = (capture.started_at, finished_at, *(p.received_at for p in capture.pages))
    if any(value is None or value.utcoffset() is None for value in times):
        return False
    if capture.started_at > finished_at:
        return False
    previous = capture.started_at
    for page in capture.pages:
        if page.received_at < previous or page.received_at > finished_at:
            return False
        previous = page.received_at
    return True


def event_matches_request(
    args: tuple[object, ...], *, screen: str, rq_name: str, tr_code: str
) -> bool:
    """Accept only a response with the exact screen and request identity."""
    return (
        len(args) >= EVENT_IDENTITY_FIELDS
        and str(args[0]).strip() == screen
        and str(args[1]).strip() == rq_name
        and str(args[2]).strip().casefold() == tr_code.casefold()
    )


def utc_now() -> datetime:
    """Return an aware timestamp for evidence metadata."""
    return datetime.now(timezone.utc)


def normalize_rows(
    rows: tuple[Mapping[str, str], ...],
) -> tuple[Mapping[str, str], ...]:
    """Trim text only; retain unknown and ambiguous broker values verbatim."""
    return tuple(
        MappingProxyType({key: value.strip() for key, value in row.items()})
        for row in rows
    )


def normalize_capture(capture: QueryCapture) -> ReadOnlySnapshot:
    """Produce display data only after complete page evidence exists."""
    if capture.status is not QueryStatus.COMPLETE:
        return ReadOnlySnapshot(
            capture_id=capture.capture_id,
            status=capture.status,
            rows=(),
            reason="READ_ONLY_QUERY_EVIDENCE_INCOMPLETE",
        )
    rows = tuple(row for page in capture.pages for row in page.raw_rows)
    return ReadOnlySnapshot(
        capture_id=capture.capture_id,
        status=QueryStatus.COMPLETE,
        rows=normalize_rows(rows),
        reason="READ_ONLY_QUERY_COMPLETE_NOT_MANAGED",
    )


class KiwoomReadOnlyAdapter:
    """Issue only connection-state and whitelisted read-only TR calls."""

    def __init__(self, control: ControlProtocol) -> None:
        """Bind an existing QAxWidget without creating or logging in."""
        self._control = control

    def login_state(self, *, observed_at: datetime | None = None) -> LoginObservation:
        """Read GetConnectState without asserting account authentication."""
        state = int(self._control.dynamicCall("GetConnectState()"))
        return LoginObservation(
            connected=state == 1,
            observed_at=observed_at or utc_now(),
            raw_state=state,
        )

    def request(self, spec: QuerySpec, *, prev_next: str = "0") -> int:
        """Submit a read-only TR request; response capture is separate."""
        if prev_next not in {"0", "2"}:
            raise ReadOnlyQueryError("PREV_NEXT_INVALID")
        for name, value in spec.input_values.items():
            self._control.dynamicCall("SetInputValue(QString, QString)", name, value)
        result = self._control.dynamicCall(
            "CommRqData(QString, QString, int, QString)",
            spec.rq_name,
            spec.tr_code,
            int(prev_next),
            "readonly",
        )
        return int(result)


def new_capture(
    spec: QuerySpec,
    *,
    account_alias: str,
    environment: str,
    started_at: datetime | None = None,
) -> QueryCapture:
    """Start a capture using an alias, never a raw account identifier."""
    if not account_alias or account_alias.isascii() is False:
        raise ReadOnlyQueryError("ACCOUNT_ALIAS_REQUIRED")
    safe_inputs = {
        name: "<redacted>" if name in SENSITIVE_INPUT_NAMES else value
        for name, value in spec.input_values.items()
    }
    return QueryCapture(
        capture_id=uuid4(),
        account_alias=account_alias,
        environment=environment,
        spec=QuerySpec(
            tr_code=spec.tr_code,
            rq_name=spec.rq_name,
            input_values=safe_inputs,
            fields=spec.fields,
        ),
        started_at=started_at or utc_now(),
        finished_at=None,
    )
