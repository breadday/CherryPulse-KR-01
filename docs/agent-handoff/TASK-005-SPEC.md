# TASK-005 구현 명세 — TASK-004 Review 지적사항 수정

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-004-REVIEW.md` 및 현재 작업 트리 (2026-09-10)

## 1. 목표와 범위

TASK-004 Review의 지적사항만 수정한다. 손절 주문에서 내부(local) 주문 ID와 키움 미체결/체결 주문번호(broker ID)를 명확히 분리하고, 취소 요청이 broker에서 확인되기 전에는 어떤 경로에서도 재주문하지 않도록 한다. 재시작, 부분체결, broker 조회 실패, 저장 실패, 재시도 한도, 14:40/15:20/15:35 경계의 fail-closed 동작을 fake broker와 clock-controlled 테스트로 증명한다.

`broker/kiwoom_broker.py`는 **수정하지 않는다**. 현재 broker는 `place_order()`가 `ORD_<timestamp>` local ID만 반환하고, 실제 broker 주문번호는 `get_pending_orders()`와 체결 callback의 `order_no/order_id`에서 얻을 수 있다. 따라서 engine이 제출 후 기존 pending 조회로 broker 번호를 단일 후보로 대조·바인딩한다. 조회가 비동기/빈 목록/모호한 결과여서 확정할 수 없으면 local ID를 broker ID로 복사하지 말고 자동 재주문을 중단하여 `MANUAL_INTERVENTION_REQUIRED`로 종료한다.

다음은 변경하지 않는다.

- 전략 조건, RiskGuard의 기본 판정, 일반 매도 경로와 일반 매도 timeout/cancel/retry 정책.
- `RUN_MODE=live`/실계좌 주문 설정을 완화하지 않으며, 테스트에서 키움 COM·실 broker·실주문을 사용하지 않는다.
- 조건검색을 다시 활성화하거나 stale 데이터로 새 가격 기반 stop을 만들지 않는다.
- 사용자가 만든 기존 변경사항을 되돌리거나 `condition_snapshot.json` 등 생성물을 수동 수정하지 않는다.

## 2. 현재 동작과 Review 근거

- `broker/kiwoom_broker.py:951-1026`의 `place_order()`는 paper/live 모두 `Order.order_id=ORD_...`를 반환하고 `broker_order_id`를 채우지 않는다. `engine.py:2196-2200`은 빈 broker ID를 `order.order_id`로 대체하므로 local ID가 broker ID로 저장된다.
- `engine.py:2880-2886`은 broker ID가 없을 때 local ID를 `cancel_order(order_no=...)`에 전달한다. live broker에서 이는 실제 주문번호 대조를 보장하지 않는다.
- `engine.py:2909-2950`은 pending에서 risk 주문이 사라진 경우 `CANCEL_REQUESTED`라도 confirmation timeout 전 즉시 `RETRY_PENDING`으로 바꾼다. 따라서 취소 확인 전 재주문 금지 불변조건을 위반한다.
- `core/models.py:58-70`의 `Order`에는 `purpose`, `risk_event_id`, `broker_order_id` 정식 필드가 없다. `engine.py`가 동적으로 부착한다.
- `core/order_manager.py:83-95`의 `bind_broker_order_id()`는 symbol 기준 최근 open 주문을 선택하여 risk/일반 주문 또는 다중 후보를 구분하지 않는다. risk event 기준 조회와 보수적 잔량 helper가 없다.
- `engine.py:1799-1868`, `1870-1898`은 pending 조회/계좌 조회 실패를 빈 결과로 반환하거나, event의 ID 누락·다수 후보·zero position을 완전한 reconciliation matrix로 판정하지 않는다. 재시작 시 계좌 잔량과 broker pending을 먼저 독립적으로 확보해야 한다.
- `main_live.py:959-1007`은 observation, pending sync, account sync를 하나의 try에 넣어 앞 단계 예외가 뒤 단계를 건너뛰게 하며, 종료 전 명시적 bounded/독립 시도가 없다. `on_heartbeat:1037-1050`은 `auto_shutdown()`이 risk 관찰보다 먼저 실행된다.
- 현재 테스트는 8개뿐이며 `tests/test_risk_restart_reconcile.py`, `tests/test_risk_late_session.py`가 없다. Review가 요구한 missing/ambiguous ID, pending-query exception, zero position, CANCEL_REQUESTED restart, partial/duplicate fill, retry/storage failure 및 14:40/15:20/15:35 경계가 자동 검증되지 않았다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `core/models.py`

`Order` dataclass에 기존 positional construction을 깨지 않는 기본값 필드를 `ts` 앞 또는 끝에 additive하게 추가한다.

- `purpose: str = ""` (risk 주문만 정확히 `RISK_STOP`).
- `risk_event_id: str = ""`.
- `broker_order_id: str = ""`.

`order_id`는 항상 engine의 local ID이고, broker 주문번호는 오직 `broker_order_id`에 둔다. local ID를 broker ID의 fallback으로 채우지 않는다.

### 3.2 `core/order_manager.py`

다음 helper를 추가/보강한다.

- `get_order_by_broker_id(broker_order_id)` 및 `get_open_risk_sell_order_by_event(event_id)` 또는 동등한 명시적 조회 API.
- `bind_broker_order_id(local_order_id, broker_order_id)`처럼 양 ID를 인자로 받아 risk event/context와 일관성을 검사하는 binding API. 기존 symbol 최근 주문 추정 binding은 risk fill 경로에서 사용하지 않는다.
- risk 주문만 대상으로 symbol/event/local/broker ID가 정확히 하나로 매칭되는지 판정하는 helper. 0개 또는 2개 이상은 ambiguous 결과로 반환한다.
- 부분체결 잔량 helper/계약: `max(local_qty - filled_qty, 0)`와 broker `unfilled_qty`가 모두 유효하면 작은 값, broker 값이 없으면 local 계산값을 사용한다. 음수/비정상 값은 자동 주문 수량으로 사용하지 않는다.

일반 `exists_open_order`, 일반 open sell 조회, 신규매수 중복 방지는 유지한다. broker mapping은 `broker_id -> local_id`와 Order의 `broker_order_id`를 함께 보존한다.

### 3.3 `infra/sqlite_store.py`

기존 additive migration과 `risk_events`의 `attempt_count`, `cancel_requested_at`, `last_action_at`를 재사용한다. 중복 컬럼을 만들지 않는다.

- risk event의 state, local ID, broker ID, qty, attempt, cancel timestamp, last action/error를 한 번의 검증 가능한 update로 기록한다.
- `update_risk_event`, `get_risk_event`, `get_open_risk_events`의 SQLite 예외를 빈 성공값으로 삼지 않는다. 호출자가 예외/실패를 감지해 manual intervention으로 fail-closed 하도록 한다.
- `include_manual=False`에서는 `MANUAL_INTERVENTION_REQUIRED`를 자동 처리 대상에서 제외하고, 관찰/복구 진단만 `include_manual=True`로 허용한다.

### 3.4 `engine.py`

#### ID 생성·제출: `_submit_risk_sell`, `_record_order_snapshot`, `_get_open_risk_order`

- 제출 전에 local ID는 broker가 준 `Order.order_id`로 유지하되 `broker_order_id=""`로 초기화하고 event에 local ID만 먼저 durable하게 저장한다.
- `broker_order_id = local_order_id` fallback을 제거한다. `cancel_order`에는 broker ID가 확정된 경우에만 전달한다. 미확정이면 cancel/retry를 하지 말고 상태와 사유를 기록한다.
- 제출 직후 기존 `broker.get_pending_orders()`를 이용해 동일 symbol/SELL/risk context/수량·시간 창의 후보를 찾고, 정확히 한 broker `order_no`일 때만 local↔broker를 원자적으로 bind한다. 후보 없음, pending 조회 예외, 다수 후보, side/symbol 불일치는 성공으로 간주하지 않고 manual intervention으로 전환한다. 이 조회는 broker adapter 수정 없이 가능한 범위이며, broker가 아직 번호를 반환하지 않는 구조적 경우에는 자동 재전송하지 않는다.
- fill callback에서 broker `fill.order_id`가 먼저 오면 기존 mapping, event의 broker ID, 또는 해당 symbol의 단 하나의 열린 risk 주문만으로 명확히 resolve한다. 다중 가능/미확정이면 portfolio/PnL/event를 추정 반영하지 말고 manual intervention 로그를 남긴다.
- `_get_open_risk_order`는 `purpose == RISK_STOP`, side SELL, event/local/broker 관계가 일치하는 주문만 반환하고 동일 event에 둘 이상이면 안전하게 실패한다.

#### 취소/재주문: `_check_stale_risk_order`, `_reconcile_risk_event`, `_process_risk_retry`, `manage_pending_orders`

- timeout 후 cancel 성공(`0`/`None`)은 `CANCEL_REQUESTED` 접수일 뿐이다. `cancel_requested_at`과 broker ID를 durable하게 저장하고, pending 대조가 확인되기 전 registry 삭제·CANCELED 전환·`RETRY_PENDING` 전환·재주문을 모두 금지한다.
- `CANCEL_REQUESTED`에서 pending이 계속 보이면 상태/매핑/부분체결 잔량을 보존하고 cancel 호출과 place 호출을 추가하지 않는다.
- pending에서 사라져도 confirmation timeout 전에는 “취소 확인”으로 취급하지 않는다. 반드시 timeout 이후에도 broker 조회가 성공했고, broker terminal/부재 및 계좌 보유 잔량이 일관되게 확인된 경우에만 `RETRY_PENDING`으로 전환한다. 조회 예외, 빈 목록을 성공으로 오인할 수 있는 상황, 식별자 누락/모호성은 manual intervention이다.
- confirmation timeout 초과로도 확정 대조가 안 되면 `MANUAL_INTERVENTION_REQUIRED`; 이후 heartbeat/tick에서 cancel/retry/place 호출은 0건이다.
- retry는 risk event별 durable attempt count와 retry delay를 사용한다. max 초과, reject, exception, 수량/ID 불일치, SQLite update/query 실패는 manual intervention이며 일반 `_retry_sell_after_cancel`, `pending_resell`, `cancel_in_progress`로 우회하지 않는다.
- 재주문은 이전 broker 주문의 terminal 확정과 보유 잔량 확인 뒤에만 가능하며, 동일 parent `risk_event_id`/idempotency key를 유지한다. 수량은 현재 portfolio 잔량과 broker 확인 잔량 중 유효한 작은 값이다. 0이면 주문하지 않고 `CLOSED`로 기록한다.
- `manage_pending_orders`는 risk event/order를 일반 주문 dispatcher보다 먼저 분리한다. risk 경로에서는 일반 매도 gate와 일반 retry/cancel 상태를 호출하지 않는다.

#### 재시작: `sync_account`, `sync_pending_orders`, `_restore_risk_events`

재시작 복구는 계좌 보유수량과 broker pending 조회를 각각 성공 여부까지 확인한 뒤 event별로 다음 matrix를 적용한다.

1. 보유 잔량 0: 추가 주문 없이 `CLOSED`, stale local registry가 있어도 broker cancel/retry 금지.
2. event broker ID와 동일한 pending SELL: 기존 local ID와 broker ID/context를 복구, partial이면 broker unfilled 잔량 보존, 주문 0건.
3. `CANCEL_REQUESTED`: pending 부재가 보여도 confirmation timeout 전 재주문 0건. timeout 후에도 확정 대조 실패면 manual.
4. broker terminal/취소 확정 + 잔량 > 0 + retry budget: `RETRY_PENDING`만 기록하고 retry delay 후 risk-only 재주문.
5. pending 조회 예외/계좌 조회 실패, event local 또는 broker ID 누락, symbol/side/order ID 다중 후보: manual intervention, 빈 목록 성공 처리 및 자동 재전송 금지.

복구 시 동일 pending을 두 번 register하지 않으며 `Order.order_id`와 `Order.broker_order_id`를 서로 바꾸지 않는다.

#### 체결: `on_fill`, `_normalize_fill_qty`

- broker fill ID를 broker ID로 취급하고 local ID로 덮어쓰지 않는다. 명확한 mapping 후에만 `OrderManager.apply_fill`을 호출한다.
- cumulative chejan/unfilled 보고를 기존 normalization으로 delta화하되, 동일 체결 callback은 qty, portfolio, realized PnL, risk event를 두 번 반영하지 않는다.
- partial fill은 `SELL_PARTIAL`과 남은 수량을 기록하고, pending broker order가 살아 있는 동안 cancel/retry하지 않는다. full fill/position zero는 `SELL_FILLED` 또는 `CLOSED` terminal로 남긴다.

#### heartbeat/shutdown 관찰: `observe_risk_events`, `main_live.py` 호출부와 bounded helper

- stale tick/reconnect 부재로 `STOP_DETECTED` 또는 새 stop을 만들지 않고, 열린 risk/cancel/manual/잔량 상태는 장외에도 관찰·로그·알림한다.
- `main_live.py:on_heartbeat`에서 `auto_shutdown` 전에 risk observation/reconciliation을 bounded하게 시도하거나, shutdown 진입 시 중복 호출을 안전하게 억제한다. 15:35 이후 새 주문은 만들지 않는다.
- `shutdown`에서 observation, `sync_pending_orders`, `sync_account`를 각각 독립 `try`/bounded timeout으로 시도한다. 하나가 실패해도 뒤의 시도는 실행하며, 실패를 성공/빈 결과로 포장하지 않는다. watchdog/os._exit 전 열린 risk 상태를 로그/Telegram으로 남긴다.
- timeout 구현은 실제 무한 `QEventLoop`/sleep을 추가하지 않는다. 기존 broker 호출이 동기식으로 무한 대기할 수 있으면 engine/main의 bounded wrapper 또는 worker/future timeout으로 호출을 격리하고 timeout 시 manual intervention으로 기록한다. 테스트는 실제 sleep/COM 없이 fake clock·주입된 callable로 검증한다.

### 3.5 `main_live.py`

- `_recover_broker_session`: `14:40` 이후 reconnect 보류 정책을 유지한다. 보류를 연결 성공/위험 상태 성공으로 기록하지 않으며 heartbeat의 risk 관찰은 계속한다.
- `on_heartbeat`: market phase와 stale recovery gate와 독립적으로 risk observation/reconciliation을 수행한다. `15:20` 이후 stale recovery는 계속 차단하지만 이미 제출된 risk 주문의 pending/timeout/manual 상태 확인은 유지한다.
- `shutdown`/`auto_shutdown`: 15:35 경계에서 final account/pending reconciliation을 독립적으로 bounded 시도한 뒤 종료한다. 계좌 sync 예외 때문에 pending sync가 생략되지 않고, pending 예외 때문에 account sync가 생략되지 않는다. 종료 중 새 risk 주문/조용한 event 삭제는 금지한다.

### 3.6 테스트 파일

기존 `tests/test_risk_guard.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_event_recovery.py`, `tests/test_risk_sell_state_machine.py`는 유지하고 필요한 회귀를 확장한다.

- `tests/test_risk_restart_reconcile.py` 신규: 실제 `SQLiteStore(tmp_path)`에 event를 만들고 새 engine을 생성한다. fake broker가 local ID와 다른 broker order number를 반환하는 pending을 제공해야 한다. 동일 pending 복구/중복 register 없음, partial 40/100 잔량 60, zero position close, missing local/broker ID, ambiguous symbol/side/order, pending 조회 exception, account 조회 exception, `CANCEL_REQUESTED` timeout 전 재주문 0건과 timeout 후 manual을 검증한다.
- `tests/test_risk_late_session.py` 신규: datetime/clock monkeypatch 또는 주입 clock으로 정확히 `14:40`, `15:20`, `15:35` 및 1분 전/후를 검증한다. reconnect/stale recovery blocked, risk observation 유지, stale 가격만으로 stop 0건, shutdown final sync 독립 시도와 bounded timeout, 예외 후에도 다른 sync 시도를 검증한다. `os._exit`는 patch한다.
- `tests/test_risk_sell_state_machine.py` 확장: local≠broker ID cancel 번호, 제출 후 broker ID 미확정 fail-closed, pending 지속, cancel failure/exception, cancel confirmation timeout 전 disappearance 재주문 금지, partial/duplicate fill, retry limit/reject/submit exception/SQLite update failure, broker 잔량과 portfolio 잔량 중 작은 수량을 포함한다.
- fake broker는 `place_order` 반환 local ID, pending의 별도 `order_no`, pending query 결과/예외, cancel 기록/반환값, partial fill, account sync 결과/예외, reconnect 상태를 주입한다. 테스트는 실계좌·키움 COM·실제 `sleep`·실제 `os._exit`를 사용하지 않는다.

## 4. 불변조건 및 안전 제약

1. `Order.order_id`는 local ID, `Order.broker_order_id`와 SQLite `broker_order_id`는 broker 주문번호다. 둘은 동일 값으로 대체하지 않는다.
2. 동일 risk event에 열린 risk SELL은 최대 하나다. `CANCEL_REQUESTED` confirmation 전 `place_order` 호출은 항상 0건이다.
3. broker API 성공은 체결 성공이 아니다. fill 또는 성공한 account/pending reconciliation 전에는 미체결로 유지한다.
4. pending 조회 예외·빈/모호한 결과·storage 실패는 성공으로 축약하지 않고 `MANUAL_INTERVENTION_REQUIRED`로 fail-closed 한다.
5. partial fill/누적 chejan은 delta만 반영하며 portfolio/PnL/event의 중복 반영을 금지한다.
6. `SELL_FILLED`, `CLOSED`, `MANUAL_INTERVENTION_REQUIRED`는 자동 재주문하지 않는 terminal 상태다.
7. retry delay/max count와 ID mapping은 durable event에 보존하며 무한 cancel/retry loop를 허용하지 않는다.
8. risk 경로는 일반 매도 시간 gate, `pending_resell`, 일반 cancel/retry flag, news/cache/trend 조건에 의존하지 않는다.
9. stale/reconnect 부재는 새 가격 기반 stop을 만들지 않는다. 유효 tick에서만 RiskGuard가 stop을 감지한다.
10. 14:40 reconnect 보류, 15:20 stale recovery 중지, 15:35 auto shutdown 경계 정책을 완화하지 않는다.
11. Python 3.8 compile/test 가능하고 기존 일반 매도·RiskGuard 회귀가 없어야 한다.
12. 로그/DB/알림에는 가능한 경우 event ID, local ID, broker ID, symbol, qty, state, reason, attempt가 포함되며 계좌 비밀값은 포함하지 않는다.

## 5. Acceptance tests

### ID 및 제출

1. fake broker가 local `ORD_LOCAL_1`, pending broker `KR_BROKER_77`을 제공하면 event/Order에 각각 다른 값이 저장되고 cancel에는 `KR_BROKER_77`만 전달된다.
2. 제출 후 broker ID가 조회되지 않거나 조회가 예외/다수 후보이면 local ID를 broker ID로 저장하지 않고 manual intervention, cancel/retry/place 추가 0건이다.

### 취소·재주문 상태 머신

3. timeout 후 cancel 호출은 1회, `CANCEL_REQUESTED`; pending 지속 시 추가 cancel/place 0건이다.
4. `CANCEL_REQUESTED` 주문이 pending에서 사라져도 confirmation timeout 전에는 `CANCEL_REQUESTED` 유지 및 place 0건이다.
5. confirmation timeout 후 broker 대조가 없거나 실패하면 `MANUAL_INTERVENTION_REQUIRED`, 이후 tick/heartbeat에도 place 0건이다.
6. cancel 실패/예외, retry max 초과, risk reject/submit exception, SQLite update/query 실패는 manual이며 일반 매도 retry로 우회하지 않는다.
7. pending 소멸, broker terminal 확정, 보유 잔량 확인이 모두 끝난 뒤에만 `RETRY_PENDING` 및 risk-only 재주문이 가능하다. 재주문 수량은 portfolio/broker 잔량의 유효한 작은 값이다.

### 재시작·부분체결·체결 조회

8. 새 engine이 기존 event와 동일한 broker pending SELL을 찾으면 local/broker/context를 복구하고 주문 0건이다.
9. 동일 pending을 반복 sync해도 Order가 중복 등록되지 않으며 partial 40/100의 unfilled 60을 보존한다.
10. 재시작 후 position zero이면 `CLOSED`이고 broker 주문 0건이다.
11. pending/account 조회 exception, event ID 누락, broker/local ID 누락, symbol/side/order 다중 후보는 manual이며 빈 목록 성공/자동 재전송이 없다.
12. partial fill 후 `SELL_PARTIAL`과 잔량이 정확하고, 같은 cumulative fill callback을 두 번 보내도 position/PnL/qty가 한 번만 변한다. full fill은 terminal이다.
13. 재시작 `CANCEL_REQUESTED` event는 timeout 전 broker pending 부재만으로 재주문되지 않는다.

### stale/reconnect/장마감

14. `14:39`, `14:40`, `14:41`에서 reconnect 허용/경계 차단을 확인하고, 차단 중에도 열린 risk observation/알림이 실행되며 reconnect 성공으로 기록되지 않는다.
15. `15:19`, `15:20`, `15:21`에서 stale recovery가 경계 이후 차단되지만 heartbeat risk observation은 실행되고 stale price만으로 stop 주문은 0건이다.
16. `15:34:59`, `15:35:00`, `15:35:01`에서 auto shutdown 경계, final risk/account/pending 시도, 새 주문 0건을 확인한다.
17. shutdown에서 pending sync가 예외여도 account sync가 시도되고, account sync가 예외여도 pending sync가 시도된다. 각 호출은 주입된 timeout 내 반환되며 실패는 로그/manual로 남는다.
18. 유효 tick이 실제 도착하면 기존 risk priority가 유지되어 일반 매도 gate와 무관하게 stop을 제출하고, 유효 tick이 없으면 stop 주문은 0건이다.
19. 기존 전체 pytest, Python 3.8 compile check, `git diff --check`가 통과한다.

## 6. 검증 명령

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/models.py','core/risk_guard.py','core/order_manager.py','engine.py','infra/sqlite_store.py','main_live.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

live 실행, 키움 연결, 실계좌 주문, 실제 `os._exit`는 검증에 사용하지 않는다. 테스트 결과에는 신규 파일별 실행 수와 failure-path 결과를 명시한다.

## 7. 롤백 고려사항

- 배포 전 SQLite 파일을 백업한다. schema 변경은 additive만 허용하고 기존 risk event/order/fill/trade를 삭제하지 않는다.
- 롤백 단위는 `engine.py` ID binding/reconcile/state machine, `core/models.py` metadata, `core/order_manager.py` helper, `infra/sqlite_store.py` fail-closed update/query, `main_live.py` bounded shutdown/heartbeat, 신규 테스트로 분리한다. `broker/kiwoom_broker.py`는 변경하지 않았으므로 되돌릴 대상이 아니다.
- 이미 broker에 제출된 주문은 코드 롤백 중 취소하거나 재전송하지 않는다. 계좌 잔량과 broker pending을 먼저 대조하고 local/broker ID 감사 기록을 보존한 뒤 수동 처리한다.
- 구현이 불완전하거나 ID/DB/broker 대조가 실패하면 일반 매도 경로로 우회하지 않고 `MANUAL_INTERVENTION_REQUIRED`로 둔다.
- 구버전/신버전 프로세스가 같은 DB를 동시에 소유하지 않도록 자동매매를 중지하고 단일 프로세스로 전환한다. 구버전이 broker ID를 local ID로 오인할 수 있는 상태에서 재시작하지 않는다.
