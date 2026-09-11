from infra.sqlite_store import SQLiteStore


def test_risk_event_is_durable_and_recovered(tmp_path):
    store = SQLiteStore(tmp_path / "risk.sqlite3")
    event = store.create_risk_event(event_id="e1", idempotency_key="k1", symbol="A", qty=10, state="STOP_DETECTED")
    assert event["event_id"] == "e1"
    assert store.create_risk_event(event_id="different", idempotency_key="k1", symbol="A", qty=10)["event_id"] == "e1"
    store.update_risk_event("e1", state="SELL_PARTIAL", local_order_id="o1")
    assert store.get_open_risk_events()[0]["local_order_id"] == "o1"
    store.update_risk_event("e1", state="SELL_FILLED")
    assert store.get_open_risk_events() == []
