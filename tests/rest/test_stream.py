"""Synthetic protocol evidence must not imply market/session/order readiness."""

from datetime import datetime, timedelta, timezone

import pytest

from adapters.kiwoom_rest_stream import QuoteStreamState

NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)


def real(**patch: object) -> dict[str, object]:
    row: dict[str, object] = {
        "type": "0B",
        "item": "005930",
        "values": {"10": "-070000", "20": "090501"},
    }
    row.update(patch)
    return {"trnm": "REAL", "data": [row]}


def registered() -> QuoteStreamState:
    state = QuoteStreamState(("005930",))
    state.begin()
    assert not state.consume({"trnm": "LOGIN", "return_code": 0}, NOW)
    assert state.registration()["data"] == [{"item": ["005930"], "type": ["0B"]}]
    assert not state.consume({"trnm": "REG", "return_code": "0"}, NOW)
    return state


def test_login_and_registration_are_not_live_quotes() -> None:
    state = registered()
    assert not state.usable("005930", NOW, max_age_seconds=2)
    assert state.reason == "NO_QUOTE"
    quotes = state.consume(real(), NOW)
    assert len(quotes) == 1
    assert quotes[0].price == 70000
    assert quotes[0].exchange_clock == "090501"
    assert state.usable("005930", NOW, max_age_seconds=2)
    assert not state.usable("005930", NOW + timedelta(seconds=3), max_age_seconds=2)
    assert not hasattr(quotes[0], "trading_day")


def test_disconnect_clears_freshness_and_reconnect_requires_new_quote() -> None:
    state = registered()
    first = state.consume(real(), NOW)[0]
    state.disconnect()
    assert not state.usable("005930", NOW, max_age_seconds=2)
    state.begin()
    assert not state.consume(real(), NOW)
    state.consume({"trnm": "LOGIN", "return_code": 0}, NOW)
    state.consume({"trnm": "REG", "return_code": 0}, NOW)
    assert not state.usable("005930", NOW, max_age_seconds=2)
    second = state.consume(real(), NOW)[0]
    assert second.generation == first.generation + 1


@pytest.mark.parametrize("code", [None, False, 3, "3"])
def test_login_without_explicit_success_stays_closed(code: object) -> None:
    state = QuoteStreamState(("005930",))
    state.begin()
    state.consume({"trnm": "LOGIN", "return_code": code}, NOW)
    assert not state.logged_in
    with pytest.raises(ValueError, match="LOGIN_UNCONFIRMED"):
        state.registration()
    assert not state.consume(real(), NOW)


@pytest.mark.parametrize(
    "patch",
    [
        {"type": "00"},
        {"item": "000660"},
        {"values": {}},
        {"values": {"10": "0", "20": "090501"}},
        {"values": {"10": 70000, "20": "090501"}},
        {"values": {"10": "1e5", "20": "090501"}},
        {"values": {"10": "70,000", "20": "090501"}},
        {"values": {"10": "70000", "20": "250501"}},
        {"values": {"10": "70000", "20": "90501"}},
    ],
)
def test_malformed_or_other_event_types_do_not_become_quotes(
    patch: dict[str, object],
) -> None:
    state = registered()
    assert not state.consume(real(**patch), NOW)
    assert not state.last_quotes


@pytest.mark.parametrize(
    "frame", [None, [], {"trnm": []}, {"trnm": "REAL", "data": []}]
)
def test_invalid_frame_is_safe(frame: object) -> None:
    state = registered()
    assert not state.consume(frame, NOW)


def test_clock_rollback_invalidates_price() -> None:
    state = registered()
    assert state.consume(real(), NOW)
    assert not state.consume(real(), NOW - timedelta(seconds=1))
    assert state.reason == "CLOCK_UNCERTAIN"
    assert not state.last_quotes


def test_registration_failure_and_duplicate_login_clear_price() -> None:
    state = registered()
    state.consume(real(), NOW)
    state.consume({"trnm": "REG", "return_code": 3}, NOW)
    assert not state.usable("005930", NOW, max_age_seconds=2)
    state.consume({"trnm": "LOGIN", "return_code": 0}, NOW)
    assert not state.registered


@pytest.mark.parametrize("symbols", [(), ("bad",), ("005930", "005930")])
def test_invalid_symbols_block_before_connect(symbols: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="SYMBOLS_INVALID"):
        QuoteStreamState(symbols)


def test_ping_preserves_state_without_claiming_price() -> None:
    state = registered()
    state.consume({"trnm": "PING"}, NOW)
    assert not state.last_quotes
    assert state.reason == "NO_QUOTE"
