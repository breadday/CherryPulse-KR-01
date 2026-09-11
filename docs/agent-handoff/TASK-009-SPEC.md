# TASK-009 구현 명세 — TASK-008 Review 지적사항만 수정

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-008-REVIEW.md` 및 현재 작업 트리 (2026-09-10)

## 1. 목표와 엄격한 범위

TASK-008 Review에서 지적한 네 가지 결함만 수정한다.

1. 14:40, 15:20, 15:35 경계의 recovery/shutdown 동작을 실제 테스트로 고정한다.
2. shutdown이 시작된 뒤 heartbeat/timer/callback 경로에서 신규 `place_order`와 `cancel_order`가 발생하지 않게 한다. 정확히 `AUTO_SHUTDOWN_HHMM == 15:35`부터 fail-closed다.
3. broker ID binding 실패가 발생한 risk sell/pending 복구 경로에서 local order, 양방향 mapping, `risk_order_events`, `sell_in_progress` 및 durable risk event가 서로 모순되지 않게 정리한다.
4. 한 risk event의 pending/account/query/identity 오류가 다른 open risk event를 `MANUAL_INTERVENTION_REQUIRED`로 바꾸지 않게 한다.

수정 허용 파일은 원칙적으로 `main_live.py`, `engine.py`, 기존 또는 신규 관련 테스트 파일로 한정한다. `core/order_manager.py`는 현재의 fail-closed binding 계약만 사용하고, 불가피한 atomic helper 추가가 필요할 때에만 수정한다. `broker/kiwoom_broker.py`, `.env`, live trading 활성화 설정, transport API, SQLite schema/API, 전략/조건검색 로직은 수정하지 않는다. 현재 작업 트리의 TASK-008 이전 무관한 변경은 되돌리거나 정리하지 않는다.

## 2. 현재 동작과 Review 근거

- `main_live.py:on_heartbeat()`는 현재 `engine.observe_risk_events()`와 `engine.manage_pending_orders()`를 먼저 호출한 뒤 `auto_shutdown()`을 호출한다. 따라서 15:35 이상에서도 pending 관리가 먼저 risk cancel/retry/place 경로에 들어갈 수 있다.
- `main_live.py:_recover_broker_session()`에는 이미 `now_hhmm >= AUTO_SHUTDOWN_HHMM` guard가 있지만, 호출자가 shutdown 전에 order management를 실행하는 문제를 막지 못한다. 14:40/15:20 독립 cutoff를 되살려서는 안 된다.
- `main_live.py:shutdown()`은 `self.shutting_down = True`를 설정하지만 그 시점에 `TradingEngine.is_running`은 아직 true이고, 종료 전 reconciliation이 수행된다. 외부 timer/callback이 경합하면 engine 내부 place/cancel 방어가 필요하다.
- `engine.py:sync_pending_orders()`는 복원 주문을 `register()`한 후 binding한다. binding 실패 시 rollback은 일부 구현되어 있으나, `engine._submit_risk_sell()`는 broker `place_order()` 후 local order/risk mapping을 만든 다음 binding 실패 시 local order와 `sell_in_progress`를 남긴다.
- `engine.py:_mark_open_risk_manual()`은 인자 없이 모든 open risk event를 순회한다. `sync_pending_orders()`의 malformed item, identity mismatch, pending query exception이 이 helper를 호출하면 원인과 무관한 다른 event까지 manual 상태가 된다.

## 3. 변경 대상과 구현 계약

### 3.1 `main_live.py` — shutdown/recovery ordering

대상 심볼: `AUTO_SHUTDOWN_HHMM`, `_recover_broker_session()`, `shutdown()`, `auto_shutdown()`, `on_heartbeat()` 및 테스트 가능한 최소 시간 helper.

- 14:40은 reconnect 금지선이 아니다. 14:39/14:40/14:41에서 cooldown, Kiwoom restart window, max-recovery limit이 없으면 `_recover_broker_session()`의 fake broker connect 경로가 동일하게 허용되어야 한다.
- 15:19/15:20/15:21 및 15:34에는 stale-realdata recovery eligibility를 유지한다. 단, 기존 stale idle, watch-code, cooldown/backoff/max-recovery 조건은 유지한다.
- `on_heartbeat()`는 `auto_shutdown()`을 risk/pending management보다 먼저 호출한다. `auto_shutdown()`으로 `shutting_down`이 true가 되면 즉시 return하여 해당 heartbeat에서 신규 order action을 시작하지 않는다. 15:35 이상에서는 recovery도 호출하지 않는다.
- `shutdown()` 진입 즉시 engine에도 shutdown gate를 전달한다. gate가 설정된 뒤 종료 전 `observe_risk_events`, `sync_pending_orders`, `sync_account`는 상태 관찰/대조만 수행하며 broker `place_order`/`cancel_order`를 시작하지 않아야 한다.
- direct caller, QTimer, signal callback 경합을 고려하여 main-level ordering만을 안전장치로 삼지 않는다. engine-level gate는 별도의 방어선이어야 한다.
- 15:35 경계에서 `shutdown()` stub을 사용하는 테스트는 `os._exit(0)`를 호출하지 않게 한다. 테스트가 실제 QApplication, COM, Kiwoom 연결을 요구해서는 안 된다.

### 3.2 `engine.py` — shutdown 신규 주문/취소 차단

대상 심볼: `TradingEngine.__init__`, `stop()`, `manage_pending_orders()`, `_submit_risk_sell()`, `_submit_auto_sell()`, `_retry_sell_after_cancel()`, `_check_stale_sell_order()`, `_check_stale_risk_order()` 및 이들로 이어지는 cancel/place 공통 경로.

- `shutdown_requested`/동등한 명시적 상태를 engine에 두고, `main_live.shutdown()`이 `shutting_down`을 세운 직후 설정한다. 상태는 정상 `start()` 전환 시에만 초기화하며, shutdown 중 race에서 false로 되돌리지 않는다.
- shutdown gate가 설정된 경우 `manage_pending_orders()`는 broker I/O와 `_submit_*`, retry, cancel을 수행하지 않고 관찰/로그 후 반환한다. `_submit_risk_sell`와 일반 `_submit_auto_sell`도 broker `place_order` 전에 gate를 확인한다.
- `_check_stale_sell_order`와 `_check_stale_risk_order`는 broker `cancel_order` 직전에 gate를 재확인한다. 이미 in-flight인 broker 호출을 임의로 취소하지는 않지만, gate 이후 새 호출을 시작하지 않는다.
- `stop()`의 기존 broker shutdown 및 알림 흐름은 유지한다. 단, gate 설정으로 인해 종료 전 reconciliation이 신규 주문/취소를 만들지 않아야 한다. API timeout/backoff 및 기존 보유종목 기록을 약화하지 않는다.

### 3.3 `engine.py` — broker ID binding 원자성/정리

대상 심볼: `sync_pending_orders()`, `_submit_risk_sell()` 및 필요 시 작은 private rollback helper.

- binding 전 snapshot에 `OrderManager.orders`, `local_to_broker_id`, `broker_to_local_id`, 각 기존 order의 `broker_order_id`, `risk_order_events`, `sell_in_progress`, 해당 durable event의 identity/state를 포함한다.
- pending 복구 binding 실패 시 새로 만든 restored local order와 모든 신규 mapping을 제거하고, 기존 order/mapping/field/event map을 호출 전 상태로 복원한다. 기존 local order를 덮어쓰지 않는다.
- `_submit_risk_sell()`의 broker `place_order`가 이미 성공한 뒤 ID binding이 실패하면 broker 주문을 취소하거나 재전송하지 않는다. local order는 미확인 broker identity를 가진 open order로 남겨두지 말고 registry에서 제거한다. `local_to_broker_id`, `broker_to_local_id`, `risk_order_events`의 해당 신규 항목을 제거하고 `sell_in_progress`도 해제한다.
- durable risk event는 삭제하지 않는다. 해당 event를 `MANUAL_INTERVENTION_REQUIRED`로 전환하고 `last_error`에 binding 실패 원인을 남긴다. 새 local/broker identity를 지우거나, 실제로 확인되지 않은 broker ID를 기록하지 않는다. 결과는 “broker 주문은 transport상 이미 제출되었을 수 있으나 identity 미확인, 자동 후속 place/cancel 금지, 수동 대조 필요”로 일관되어야 한다.
- binding 성공 시에만 `Order.broker_order_id`와 양방향 mapping, `risk_order_events`를 기록한다. 동일 pending을 두 번 동기화해도 order/mapping은 1개뿐이어야 한다.
- 기존 `OrderManager.bind_broker_order_id()`의 local==broker, unknown local, event mismatch, broker/local 충돌 fail-closed 계약을 깨지 않는다.

### 3.4 `engine.py` — risk event 오류 격리

대상 심볼: `_mark_open_risk_manual()` 및 이를 호출하는 `sync_pending_orders()`, `sync_account()`, `_reconcile_risk_event()`/복구 경로.

- `_mark_open_risk_manual()`은 event id 또는 정확히 식별 가능한 local/broker identity를 선택 인자로 받아 해당 event 하나만 갱신하도록 바꾼다. broad “모든 open event” 동작을 production error path에서 사용하지 않는다.
- malformed pending item, symbol/side/quantity mismatch, duplicate/ambiguous identity는 가능한 경우 해당 broker order ID/local/event에 매칭되는 event만 manual 처리한다. 매칭되지 않으면 어떤 기존 event도 상태 변경하지 않고 manual-intervention 로그만 남긴다.
- pending/account query exception은 특정 event의 실패로 가장하지 않는다. 전체 open event를 manual로 일괄 변경하지 않고, 예외/재시도 금지/수동 확인 필요를 로그로 남긴 뒤 예외 전파 여부는 기존 contract를 유지한다. 오류가 이미 event 단위 reconciliation에서 발생한 경우에는 그 event만 manual 처리한다.
- `_reconcile_risk_event()`는 현재처럼 event별로 처리하며, 한 event의 pending 예외·missing·ambiguous·binding 실패가 다음 event loop를 중단시키거나 다른 event를 변경하지 않게 한다. 각 event 처리는 독립 try/except 또는 동일 효과의 isolation을 가져야 한다.
- 모든 ambiguous/missing/exception 경로에서 자동 `place_order`와 `cancel_order`는 0회다. 오류를 빈 pending/성공/확정 취소로 축약하지 않는다.

## 4. 불변조건과 안전 제약

1. `AUTO_SHUTDOWN_HHMM` 이상에서는 새로운 reconnect/stale recovery 및 새로운 place/cancel이 시작되지 않는다. 정확히 15:35는 shutdown 경계다.
2. 14:40/15:20은 독립 cutoff가 아니며 14:39·14:40·14:41, 15:19·15:20·15:21의 정상 recovery eligibility가 보존된다.
3. shutdown gate 이후 fake broker의 `place_calls == 0`, `cancel_calls == 0`이어야 한다. 이미 broker에 제출된 주문을 테스트 rollback이 취소하지 않는다.
4. binding 실패는 local order, 양방향 mapping, order broker field, in-memory risk map, in-progress set의 부분 상태를 남기지 않는다.
5. binding 실패 durable event는 삭제하지 않고 수동개입 상태로 남기며, 확인되지 않은 broker identity를 새로 기록하지 않는다.
6. risk event A의 오류는 risk event B의 state/identity/mapping을 변경하지 않는다.
7. 부분체결 및 cumulative fill idempotency, `CANCEL_REQUESTED` confirmation timeout, 보유 포지션 감시와 기존 timeout/backoff/max-recovery 동작은 회귀하지 않는다.
8. `broker/kiwoom_broker.py`, `.env`, live trading enablement, SQLite schema/API는 diff에 없어야 한다. 모든 테스트는 fake broker와 temporary SQLite만 사용한다.

## 5. Acceptance tests

### 5.1 `tests/test_main_live_recovery_window.py` (신규 권장)

실제 QApplication/COM 없이 `MainLiveApp.__new__` 또는 기존 최소 fixture를 사용한다. `_now_hhmm`, `time.time`, broker connection, shutdown을 stub한다.

- 14:39/14:40/14:41: `_recover_broker_session("broker_disconnected")`가 early cutoff 때문에 차단되지 않고 fake `connect()`를 허용한다.
- 15:19/15:20/15:21 및 15:34: stale idle tick 조건에서 `_recover_broker_session("stale_realdata:180s")`가 호출/허용된다.
- 15:35/15:36: `on_heartbeat()`가 `auto_shutdown()`을 먼저 호출하고 shutdown stub 이후 return하며, recovery와 engine pending management가 호출되지 않는다.
- shutdown 상태에서 heartbeat/timer/callback을 반복 호출해도 fake broker `place_calls == 0`, `cancel_calls == 0`이다. observation 호출 자체와 order action을 구분해 assertion한다.
- 직접 `_recover_broker_session()`을 15:35/15:36에 호출해도 reconnect가 호출되지 않는다.

### 5.2 `tests/test_risk_restart_reconcile.py` 또는 `test_risk_sell_state_machine.py`

- temporary SQLite에 open event A/B를 만들고 pending/query 또는 binding을 A만 실패시킨다. A만 `MANUAL_INTERVENTION_REQUIRED`가 되고 B의 state, local/broker identity, mapping은 그대로인지 확인한다.
- pending query exception 및 account query exception을 각각 독립 테스트한다. 다른 event를 일괄 manual로 만들지 않고, 예외 계약이 유지되며 `place_calls == 0`, `cancel_calls == 0`인지 확인한다.
- missing broker ID, duplicate/ambiguous symbol+side candidate, local/broker ID conflict를 각각 테스트한다. 자동 place/cancel 0회와 event 격리를 확인한다.
- `_submit_risk_sell()` broker ID binding 실패에서 broker `place_calls == 1`은 허용하되 `cancel_calls == 0`; 이후 `orders`, 양방향 mapping, `Order.broker_order_id`, `risk_order_events`, `sell_in_progress`에 신규 미확인 상태가 없고 durable event만 manual인지 확인한다.
- `sync_pending_orders()` binding 실패에서는 호출 전/후 state snapshot이 동일하고, manual event 외에 local order/mapping/event map이 변하지 않는지 확인한다.
- 성공 binding 후 동일 pending을 두 번 sync해 order 1개, 양방향 mapping 1개, partial `100/40/60` 및 `PARTIAL` 상태가 보존되는지 확인한다.
- 서로 다른 event의 cumulative fill callback `40, 40, 60`에서 중복 40이 한 번만 반영되고, 다른 event 상태가 오염되지 않는지 회귀 확인한다.

### 5.3 정적/회귀 검증

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['main_live.py','engine.py','core/order_manager.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short --untracked-files=all
```

보고서에는 신규/수정 테스트 수, 14:40/15:20/15:35 각 결과, shutdown 이후 `place_order`/`cancel_order` 호출 수, binding failure 및 event isolation별 호출 수를 명시한다. `broker/kiwoom_broker.py`, `.env`, live enablement가 diff에 없는지 확인한다.

## 6. 롤백 고려사항

- 배포 전 SQLite DB와 현재 broker pending/보유 상태를 백업·대조한다. binding 실패로 manual event가 기록된 주문은 자동 재주문/자동 취소하지 말고 broker 화면과 local DB를 수동 대조한다.
- 롤백 대상은 `main_live.py`의 heartbeat/shutdown gate, `engine.py`의 order-action gate, binding rollback, event-scoped manual 처리 및 관련 테스트뿐이다. TASK-007/008의 identity/schema 및 무관한 작업 트리 변경을 함께 되돌리지 않는다.
- 구버전 롤백은 15:35 경계에서 신규 place/cancel이 발생할 위험과 event 전역 manualization을 다시 가져올 수 있다. 롤백 중 자동매매를 중지하고 보유 포지션·미체결·risk event를 수동 감시한다.
- broker ID가 확인되지 않은 상태에서 구버전 프로세스를 재기동하지 않는다. local ID를 broker ID로 오인해 cancel/place하지 않도록 단일 프로세스와 identity 대조 후 재개한다.
