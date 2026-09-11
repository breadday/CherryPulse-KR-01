# TASK-008 구현 명세 — TASK-007 Review 지적사항만 수정

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-007-REVIEW.md` 및 현재 작업 트리 (2026-09-10)

## 1. 목표와 엄격한 범위

TASK-007 Review에서 지적된 미완성 사항만 보완한다.

1. `main_live.py`의 14:40 reconnect 차단과 15:20 stale-realdata recovery 차단을 제거/재정의하여 보유 포지션 및 미체결 위험 감시·복구가 `AUTO_SHUTDOWN_HHMM == 15:35` 직전까지 동작하게 한다.
2. `TradingEngine.sync_pending_orders`가 broker ID binding 실패 시 `OrderManager.orders`, 양방향 mapping, `risk_order_events`를 변경하지 않는 fail-closed 상태가 되게 한다.
3. 실제 `SQLiteStore`에 저장된 risk event를 사용하여 프로세스 재시작을 모사하는 새 `TradingEngine` 테스트를 추가한다. 부분체결, 중복/누적 체결, pending/account 조회 예외 및 14:40/15:20/15:35 경계를 포함한다.

수정 허용 파일은 `main_live.py`, `engine.py`, 기존 risk 테스트 보강 및 필요한 신규 테스트 파일로 한정한다. `broker/kiwoom_broker.py`, `.env`, live trading 활성화 코드, 전략/조건검색 로직, SQLite schema/API는 수정하지 않는다. 현재 작업 트리에 이미 있는 무관한 변경은 되돌리거나 정리하지 않는다.

## 2. 현재 동작과 근거

- `main_live.py:49`의 자동 종료 시각은 `15:35`이고 `_market_phase()`는 그 시각부터 `after_close`를 반환한다.
- `main_live.py:631-662`의 `_recover_broker_session()`은 `now_hhmm >= RECONNECT_DISABLE_AFTER_HHMM` (`:58`, `14:40`)이면 reconnect를 거부하고 60초 block을 설정한다.
- `main_live.py:1043-1092`의 `on_heartbeat()`는 risk observation/pending management를 먼저 수행하지만, `:1076-1077`에서 `now_hhmm >= STALE_REALDATA_DISABLE_AFTER_HHMM` (`:62`, `15:20`)이면 stale recovery를 호출하지 않는다. 따라서 15:20~15:35의 보유 포지션 위험 감시 연결이 끊겨도 자동 복구되지 않는다.
- `main_live.py:1052-1059`의 `auto_shutdown()` 호출은 heartbeat의 recovery보다 앞서므로 15:35 이상에서는 먼저 `shutdown()`이 실행되어야 한다. 이 순서를 유지해야 장후 reconnect를 새로 허용하지 않는다.
- `engine.py:1800-1882`의 `sync_pending_orders()`는 복원 주문을 `order_manager.register()`한 뒤 `bind_broker_order_id()`를 호출한다. binding 실패 시 manual event만 기록하고 `restored_order`와 `risk_order_events[local_id]`가 남을 수 있어, 보고한 fail-closed 계약과 실제 local state가 불일치한다.
- 현재 `tests/test_risk_restart_reconcile.py`는 `OrderManager` 단위 identity만 검사한다. SQLite에 durable event를 만들고 새 `TradingEngine`으로 복구하는 end-to-end restart 검증, pending/account 예외, 시간 경계 검증은 없다. `tests/test_risk_sell_state_machine.py`에도 binding 실패 후 `orders` 불변을 직접 확인하는 검사가 없다.

## 3. 변경 대상과 구현 계약

### 3.1 `main_live.py`

대상 심볼: `RECONNECT_DISABLE_AFTER_HHMM`, `STALE_REALDATA_DISABLE_AFTER_HHMM`, `_recover_broker_session()`, `on_heartbeat()` 및 시간 경계 판정에 필요한 최소 helper.

- 14:40을 독립 reconnect 금지선으로 사용하지 않는다. `_recover_broker_session()`은 `shutting_down`, 동시 reconnect, Kiwoom 서버 restart window, cooldown/backoff/max-recovery 제한은 계속 적용하되 14:40 때문에 반환하지 않아야 한다.
- stale realdata 경로는 `STALE_REALDATA_CHECK_HHMM` 이후이면서 `AUTO_SHUTDOWN_HHMM` 미만일 때 recovery를 시도한다. 15:20은 더 이상 stale recovery cutoff가 아니다.
- cutoff 비교는 `now_hhmm >= AUTO_SHUTDOWN_HHMM`를 사용하여 정확히 15:35에는 recovery를 시작하지 않는다. `on_heartbeat()`의 `auto_shutdown()` 선행 호출 및 `shutting_down` 반환을 유지한다.
- 보유 포지션과 open order가 `_all_watch_codes()`에 포함되는 현재 감시 범위를 유지한다. stale tick recovery가 후보 유니버스에만 의존하거나 포지션 감시를 제거해서는 안 된다.
- reconnect 성공 시 기존의 account sync, pending sync, health check, snapshot/real registration 및 조건검색 처리 흐름을 유지한다. reconnect를 허용하기 위해 broker transport나 live 설정을 우회하지 않는다.
- 기존 상수명을 제거하는 경우 참조를 모두 제거하고, 유지하는 경우 값/의미가 `AUTO_SHUTDOWN_HHMM`과 모순되지 않게 한다. 시간 계산을 테스트 가능하게 만드는 helper를 추가해도 production behavior는 위 계약과 동일해야 한다.

### 3.2 `engine.py` — `TradingEngine.sync_pending_orders()`

- broker pending query 예외는 현재의 예외 전파 및 `_mark_open_risk_manual()` 동작을 유지한다. 예외를 빈 pending으로 축약하거나 local orders를 정리하지 않는다.
- 각 pending item의 수량/side/symbol/identity 검증을 먼저 수행한다. invalid 또는 binding 후보가 0개/복수/충돌이면 manual intervention을 기록하고 해당 item을 자동 복원·취소·재주문하지 않는다.
- 복원 주문은 `purpose`, `risk_event_id`, `broker_order_id` formal field를 사용하고 local ID를 broker ID로 대체하지 않는다.
- binding 성공 전에는 `risk_order_events`를 쓰지 않는다. binding 실패 경로에서 `OrderManager.orders`, `local_to_broker_id`, `broker_to_local_id`, `Order.broker_order_id`, `risk_order_events`가 호출 전 snapshot과 동일해야 한다.
- 이를 보장하는 최소 구현은 (a) binding 검증/등록을 원자적 helper로 `OrderManager`에 추가하거나, (b) 임시 register 후 실패 시 등록과 모든 부수 mapping을 완전히 rollback하는 것이다. 기존 `OrderManager.bind_broker_order_id()`의 실패 불변 계약을 깨지 않는다. 동시성/기존 local order 충돌 시 기존 주문을 덮어쓰지 않는다.
- 성공한 복원만 `restored` 카운트, event mapping 및 로그에 반영한다. 동일 broker pending을 반복 sync해도 주문 1개와 양방향 mapping 1개만 유지한다.
- partial `order_qty/filled_qty/unfilled_qty` 검증 및 `PARTIAL`/filled 수량 보존, 이후 risk event reconcile 동작은 TASK-007 계약을 유지한다. 본 작업에서 SQLite schema migration은 추가하지 않는다.

## 4. 불변조건 및 안전 제약

1. `AUTO_SHUTDOWN_HHMM` 이상에서는 reconnect/stale recovery와 새 place/cancel이 자동으로 시작되지 않는다. 정확히 15:35는 shutdown 경계다.
2. 14:40 및 15:20은 보유 포지션 위험감시를 중단시키는 cutoff가 아니다. 14:40/15:20 직전·직후 heartbeat에서 recovery eligibility가 유지된다.
3. shutdown 선행 순서, API timeout/cooldown/backoff/max-recovery, 보유종목 감시 및 pending 관리 순서를 임의로 약화하지 않는다.
4. pending binding 실패는 fail-closed다. local order/mapping/event 연결을 부분적으로 남기지 않는다.
5. pending/account 조회 예외, 누락/모호/충돌 identity는 성공·빈 결과로 처리하지 않으며 자동 주문 호출은 0회다.
6. risk event 하나당 open risk SELL은 최대 하나이고, 이미 broker에 제출된 주문을 복구 테스트나 rollback이 취소/재전송하지 않는다.
7. `broker/kiwoom_broker.py`, `.env`, live 활성화 설정은 읽기만 하고 수정하지 않는다. 테스트는 fake broker와 temporary SQLite만 사용하며 실제 COM/키움/live 주문을 실행하지 않는다.

## 5. Acceptance tests

### 5.1 시간 경계 (`tests/test_main_live_recovery_window.py` 신규 또는 기존 main 테스트 파일)

실제 `QApplication`/Kiwoom 연결 없이 `MainLiveApp`의 시간 판정 helper 또는 `__new__`로 구성한 최소 fixture를 사용한다.

- 14:39, 14:40, 14:41: reconnect block 때문에 반환하지 않고, cooldown/backoff가 없으면 `_recover_broker_session()`이 fake broker `connect()` 경로를 허용한다.
- 15:19, 15:20, 15:21: stale tick idle 조건에서 recovery가 허용된다.
- 15:34: recovery가 허용된다.
- 15:35 및 15:36: `auto_shutdown()`/`after_close` 경계가 먼저 작동하고 recovery가 호출되지 않는다. 테스트는 `shutdown`을 stub하여 `os._exit`를 호출하지 않게 한다.
- `on_heartbeat()`에서 15:35 이상에도 risk observation/pending management가 먼저 한 번 실행되는지, 그 뒤 recovery만 차단되는지 검증한다.

### 5.2 fail-closed pending binding (`tests/test_risk_sell_state_machine.py` 또는 `tests/test_risk_restart_reconcile.py`)

- 실제 `SQLiteStore(tmp_path / "risk.sqlite3")`에 open risk event를 만들고, broker pending item을 별도 local ID/broker ID로 준비한다.
- `bind_broker_order_id()`가 event mismatch, broker ID 충돌, local/broker 동일 ID 또는 기타 실패를 반환하도록 구성한다.
- `sync_pending_orders()` 전후로 `orders`, 양방향 mapping, order broker field, `risk_order_events`를 비교하여 모두 불변이고, manual 상태만 durable event에 기록되는지 검증한다.
- 정상 binding은 복원 1건을 만들며 같은 pending을 두 번 sync해도 order/mapping이 중복되지 않는다.
- pending/account query가 예외를 던지는 fake broker에서 예외가 전파되고 manual intervention이 저장되며 `place_calls == 0`, `cancel_calls == 0`인지 검증한다.

### 5.3 실제 SQLite + 새 `TradingEngine` restart (`tests/test_risk_restart_reconcile.py`)

- 첫 engine이 fake broker/temporary SQLite로 position과 stop event를 durable하게 생성하고 local ID 및 broker ID를 기록한다.
- 첫 engine을 폐기한 뒤 동일 DB로 **새 `TradingEngine`**을 생성하고 account/pending 응답을 주입한다. 새 engine이 SQLite event와 broker pending을 대조해 기존 stop을 복원하며 새 `place_order`를 호출하지 않는지 검증한다.
- 동일 pending을 두 번 sync하여 order 1개, mapping 1개, partial total 100 / filled 40 / unfilled 60 및 `PARTIAL` 상태를 보존한다.
- cumulative fill 40 callback을 두 번, 이어 60 callback을 전달하여 portfolio 수량, order filled quantity, realized PnL, risk event가 delta 한 번만 반영되고 position zero/terminal event가 `CLOSED` 또는 기존 terminal 계약으로 끝나는지 검증한다.
- `CANCEL_REQUESTED` event의 pending disappearance는 confirmation timeout 전 재주문하지 않고, timeout 후 account/pending 대조가 예외 또는 모호하면 manual intervention으로 끝나며 `place_calls == 0`, `cancel_calls == 0`인지 검증한다.
- missing event/local/broker ID, symbol/side 복수 후보, pending/account 조회 예외 각각을 독립 test case로 두고 자동 place/cancel 0회를 assertion한다.

### 5.4 회귀 및 정적 검증

다음 명령을 통과시킨다.

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['main_live.py','engine.py','core/order_manager.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
```

보고서에는 신규/수정 테스트 수와 각 failure-path의 `place_order`/`cancel_order` 호출 횟수를 명시한다. `broker/kiwoom_broker.py`, `.env`, live 활성화 코드가 diff에 없는지도 확인한다.

## 6. 롤백 고려사항

- 배포 전 SQLite DB를 백업하고, 이미 제출된 broker 주문·계좌 보유·risk event를 수동 대조한다.
- 롤백 대상은 `main_live.py`의 recovery-window 판정, `engine.py`의 pending 복구 atomicity, 관련 테스트뿐이다. TASK-007의 identity/schema 변경 및 무관한 작업 트리 변경을 함께 되돌리지 않는다.
- 구버전으로 되돌릴 때 14:40/15:20 차단이 재활성화되어 장마감 전 포지션 감시 공백이 생길 수 있으므로, 롤백 중 자동매매를 중지하고 15:35까지 보유 포지션과 미체결 주문을 수동 감시한다.
- binding 불명확 상태에서 구버전 프로세스를 재기동하지 않는다. local ID를 broker ID로 오인해 취소/재주문하지 않도록 identity를 확인한 뒤 단일 프로세스로 재개한다.
