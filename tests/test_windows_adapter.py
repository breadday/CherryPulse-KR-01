from dataclasses import replace

import pytest

from verification.windows_adapter import (
    AdapterRequest,
    ScriptedWindowsPaperAdapter,
    WindowsAdapterConfig,
)


def request(operation_id="op-1"):
    return AdapterRequest(operation_id=operation_id, symbol="005930", side="BUY", qty=10)


def test_windows_adapter_requires_declared_paper_windows_boundary() -> None:
    with pytest.raises(ValueError, match="WINDOWS_PAPER_ONLY"):
        ScriptedWindowsPaperAdapter(WindowsAdapterConfig(target_os="LINUX", environment="PAPER"))
    with pytest.raises(ValueError, match="WINDOWS_PAPER_ONLY"):
        ScriptedWindowsPaperAdapter(WindowsAdapterConfig(target_os="WINDOWS", environment="LIVE"))


def test_windows_adapter_returns_deterministic_quote_without_transport() -> None:
    adapter = ScriptedWindowsPaperAdapter(
        WindowsAdapterConfig(target_os="WINDOWS", environment="PAPER"),
        quotes={"005930": {"price": "70000", "occurred_at": "2026-09-22T06:00:00Z"}},
    )

    assert adapter.quote("005930") == {"symbol": "005930", "price": "70000", "occurred_at": "2026-09-22T06:00:00Z"}
    assert adapter.transport_calls == ()


def test_unknown_response_is_terminal_for_automatic_retry() -> None:
    adapter = ScriptedWindowsPaperAdapter(
        WindowsAdapterConfig(target_os="WINDOWS", environment="PAPER"),
        outcomes={"op-1": "TIMEOUT"},
    )

    observation = adapter.submit(request())

    assert observation.state == "UNKNOWN"
    with pytest.raises(ValueError, match="RETRY_BLOCKED_UNKNOWN"):
        adapter.submit(request())
    assert adapter.transport_calls == ("op-1",)


def test_duplicate_operation_replays_observation_and_partial_fill_is_explicit() -> None:
    adapter = ScriptedWindowsPaperAdapter(
        WindowsAdapterConfig(target_os="WINDOWS", environment="PAPER"),
        outcomes={"op-1": "PARTIAL"},
    )

    first = adapter.submit(request())
    second = adapter.submit(replace(request(), qty=99))

    assert first.state == "PARTIALLY_FILLED"
    assert first.filled_qty == 5
    assert second == first
    assert adapter.transport_calls == ("op-1",)


def test_rejected_operation_does_not_create_order_id() -> None:
    adapter = ScriptedWindowsPaperAdapter(
        WindowsAdapterConfig(target_os="WINDOWS", environment="PAPER"),
        outcomes={"op-1": "REJECT"},
    )

    observation = adapter.submit(request())

    assert observation.state == "REJECTED"
    assert observation.broker_order_id is None


def test_adapter_request_rejects_malformed_runtime_types() -> None:
    with pytest.raises(ValueError, match="ADAPTER_REQUEST_INVALID"):
        AdapterRequest(operation_id=123, symbol="005930", side="BUY", qty=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="ADAPTER_REQUEST_INVALID"):
        AdapterRequest(operation_id="op-2", symbol="005930", side=[], qty=1)  # type: ignore[arg-type]


def test_partial_outcome_rejects_zero_fill_and_records_no_transport_call() -> None:
    adapter = ScriptedWindowsPaperAdapter(
        WindowsAdapterConfig(target_os="WINDOWS", environment="PAPER"),
        outcomes={"op-1": "PARTIAL"},
    )

    with pytest.raises(ValueError, match="ADAPTER_PARTIAL_INVALID"):
        adapter.submit(replace(request(), qty=1))
    assert adapter.transport_calls == ()
