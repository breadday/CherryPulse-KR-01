from decimal import Decimal

import pytest

from verification.paper import (
    PaperBroker,
    PaperOrderRequest,
    Quote,
    ReadOnlyQuoteGateway,
    RawEventLog,
)


def test_read_only_gateway_records_quote_but_rejects_order_side_effects() -> None:
    gateway = ReadOnlyQuoteGateway(
        quotes={"005930": Quote(symbol="005930", price="70000", observed_at="2026-09-22T14:00:00Z")}
    )

    assert gateway.get_quote("005930").price == "70000"
    with pytest.raises(ValueError, match="PAPER_READ_ONLY"):
        gateway.submit_order(
            PaperOrderRequest(symbol="005930", side="BUY", quantity=1, limit_price="70000")
        )


def test_raw_event_log_replays_exact_events_once() -> None:
    log = RawEventLog()
    event = {"event_id": "evt-1", "kind": "QUOTE", "symbol": "005930", "price": "70000"}

    assert log.append(event)
    assert not log.append(event)
    assert log.replay() == (event,)


def test_raw_event_log_rejects_conflicting_duplicate_event_ids() -> None:
    log = RawEventLog()
    assert log.append({"event_id": "evt-1", "price": "70000"})

    with pytest.raises(ValueError, match="EVENT_ID_CONFLICT"):
        log.append({"event_id": "evt-1", "price": "1"})


def test_paper_broker_tracks_partial_fill_and_cancel() -> None:
    broker = PaperBroker()
    order_id = broker.submit(
        PaperOrderRequest(symbol="005930", side="BUY", quantity=10, limit_price="70000")
    )

    broker.fill(order_id, quantity=4, price="69900")
    broker.cancel(order_id)
    order = broker.order(order_id)

    assert order.quantity == 10
    assert order.filled_quantity == 4
    assert order.cancelled_quantity == 6
    assert order.remaining_quantity == 0
    assert order.state == "CANCELLED"
    assert order.average_fill_price == Decimal("69900")


def test_raw_event_log_isolated_from_nested_input_and_replay_mutation() -> None:
    log = RawEventLog()
    event = {"event_id": "evt-1", "payload": {"price": "70000"}}

    assert log.append(event)
    event["payload"]["price"] = "1"
    replayed = log.replay()
    replayed[0]["payload"]["price"] = "2"

    assert log.replay()[0]["payload"]["price"] == "70000"


def test_paper_broker_rejects_non_integer_quantities() -> None:
    broker = PaperBroker()
    for quantity in (True, 1.5):
        with pytest.raises(ValueError, match="PAPER_ORDER_REQUEST_INVALID"):
            broker.submit(
                PaperOrderRequest(
                    symbol="005930", side="BUY", quantity=quantity, limit_price="70000"
                )
            )

    order_id = broker.submit(
        PaperOrderRequest(symbol="005930", side="BUY", quantity=2, limit_price="70000")
    )
    with pytest.raises(ValueError, match="FILL_QUANTITY_INVALID"):
        broker.fill(order_id, quantity=True, price="70000")


def test_paper_broker_rejects_malformed_side_values() -> None:
    broker = PaperBroker()

    with pytest.raises(ValueError, match="PAPER_ORDER_REQUEST_INVALID"):
        broker.submit(PaperOrderRequest("005930", ["BUY"], 1, "70000"))


def test_paper_broker_rejects_non_finite_or_exponent_prices() -> None:
    broker = PaperBroker()
    for price in ("Infinity", "NaN", "1e999"):
        with pytest.raises(ValueError, match="INVALID_LIMIT_PRICE"):
            broker.submit(PaperOrderRequest("005930", "BUY", 1, price))


def test_paper_broker_enforces_submitted_limit_price_on_fills() -> None:
    broker = PaperBroker()
    buy_order = broker.submit(
        PaperOrderRequest(symbol="005930", side="BUY", quantity=1, limit_price="70000")
    )
    sell_order = broker.submit(
        PaperOrderRequest(symbol="005930", side="SELL", quantity=1, limit_price="70000")
    )

    with pytest.raises(ValueError, match="FILL_PRICE_OUTSIDE_LIMIT"):
        broker.fill(buy_order, quantity=1, price="70001")
    with pytest.raises(ValueError, match="FILL_PRICE_OUTSIDE_LIMIT"):
        broker.fill(sell_order, quantity=1, price="69999")
