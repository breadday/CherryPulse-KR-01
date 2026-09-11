# TASK-006 구현 명세 — TASK-005 Review 실패만 수정

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-005-REVIEW.md`, `TASK-005-IMPLEMENTATION.md`, 현재 작업 트리 (2026-09-10)

## 1. 목표와 범위

TASK-005 Review에서 재현된 실패와 명시적으로 남은 risk 주문 ID/상태 추적 결함만 수정한다. 핵심은 다음 네 가지다.

1. `engine.py:_check_stale_risk_order`의 unreachable/잘못된 들여쓰기를 고쳐 timeout cancel이 확정된 broker 주문번호로 실제 호출되게 한다.
2. `core.models.Order`에 risk 주문 메타데이터를 동적 속성이 아닌 정식 dataclass 필드로 추가한다.
3. `OrderManager`가 local order ID와 broker order ID를 명시적으로 양방향 연결하고, risk event 기준으로 모호하지 않은 주문만 반환하게 한다.
4. pending risk order 재조정, `CANCEL_REQUESTED` confirmation timeout, 부분체결/중복 체결, 재시작 복구를 fake broker와 임시 SQLite로 자동 검증한다.

이번 작업은 TASK-005의 fail-closed 정책을 되돌리지 않는다. broker ID가 확정되지 않거나 broker/저장소 조회가 모호하면 자동 취소·재주문 대신 `MANUAL_INTERVENTION_REQUIRED`를 유지한다.

## 2. 현재 동작과 실패 근거

- `engine.py:2911-2938`, `_check_stale_risk_order`에서 `broker_id` 계산 및 미확정 ID 검사가 `return` 아래에 들여쓰기되어 있다. 따라서 정상 risk event도 broker ID를 준비하지 못하고, cancel 호출 경로가 동작하지 않는다. TASK-005 테스트의 `test_cancel_request_waits_for_broker_disappearance`는 cancel 0회로 실패했다.
- `core/models.py:58-70`, `Order`에는 `purpose`, `risk_event_id`, `broker_order_id`가 없다. `engine.py`가 현재 인스턴스에 동적으로 부착하므로 생성·복구·타입 계약이 일관되지 않다.
- `core/order_manager.py:83-95`, `bind_broker_order_id(symbol, broker_order_id)`는 symbol 기준 최근 open 주문을 추정한다. risk/일반 매도 및 복수 주문을 구분하지 않으며 local ID를 인자로 받지 않는다.
- `engine.py:2192-2243`은 제출 후 pending의 symbol/SELL/`order_no`만 검사하고 직접 dictionary를 갱신한다. risk event/local ID와 broker ID의 명시적 binding helper를 사용해야 한다.
- `tests/test_risk_sell_state_machine.py:88-98`의 fixture는 local ID를 pending `order_no`로 재사용한다. TASK-005 계약상 이는 broker ID 미확정으로 fail-closed되어 event가 open 목록에서 제외되므로 `IndexError`가 발생한다. fixture는 local ID와 별도 broker ID를 제공해야 한다.
- 현재 `tests/`에는 `test_risk_restart_reconcile.py`가 없고, partial/restart/CANCEL timeout failure-path의 durable 동작을 충분히 검증하지 않는다. 실 broker/COM 호출은 사용하지 않는다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `core/models.py`

`Order` dataclass에 기존 positional 생성 호출을 깨지 않도록 기본값 필드를 additive하게 추가한다(기존 필수 필드와 `ts`의 기본값 규칙을 보존).

- `purpose: str = ""`
- `risk_event_id: str = ""`
- `broker_order_id: str = ""`

계약:

- `Order.order_id`는 항상 내부 local ID다.
- `Order.broker_order_id`만 broker 주문번호이며, local ID를 fallback으로 복사하지 않는다.
- 일반 주문의 기본값은 빈 문자열이고, risk stop 주문은 `purpose == "RISK_STOP"` 및 해당 `risk_event_id`를 가진다.

### 3.2 `core/order_manager.py`

다음 API를 추가/보강한다. 기존 일반 주문 조회와 `exists_open_order` 동작은 유지한다.

- `get_order_by_broker_id(broker_order_id) -> Optional[Order]`: 명시적 broker→local mapping과 Order 필드를 일관되게 조회한다.
- `get_open_risk_sell_order_by_event(event_id) -> Optional[Order]`: `purpose`, SELL, open status, 동일 event를 모두 만족하는 주문이 정확히 하나일 때만 반환한다. 0개와 2개 이상은 `None`으로 fail-closed한다.
- `bind_broker_order_id(local_order_id, broker_order_id, risk_event_id="") -> Optional[Order]` (또는 동등한 명시적 API): 두 ID를 모두 입력받아 존재하는 local order에만 binding한다. 이미 다른 local order에 연결된 broker ID, 이미 다른 broker ID를 가진 local order, risk event/context 불일치는 binding하지 않는다.

mapping은 `broker_to_local_id`와 `Order.broker_order_id`에 함께 보존한다. 부분체결 잔량 계산 helper를 둔다면 음수/비정상 값은 거부하고, 유효한 local 계산 잔량과 broker `unfilled_qty`의 작은 값을 사용하며 broker 값이 없을 때만 local 계산값을 사용한다.

### 3.3 `engine.py`

#### `_check_stale_risk_order` (약 2911행)

- event 조회/상태 확인 후 `broker_id = order.broker_order_id`를 반드시 실행 가능한 위치에서 계산한다.
- broker ID가 비어 있으면 cancel 호출 없이 event를 manual로 기록하고 return한다.
- timeout 이후 cancel 성공(`0` 또는 `None`)은 `CANCEL_REQUESTED` 접수일 뿐이다. order registry/mapping을 삭제하거나 `CANCELED`, `RETRY_PENDING`으로 바꾸지 않는다. `cancel_requested_at`, `last_action_at`, broker ID, 남은 수량을 저장한다.
- cancel 실패/예외는 manual이며 이후 일반 매도 cancel/retry 경로로 우회하지 않는다.
- 동일 event에 대해 `risk_cancel_in_progress` 및 durable state로 중복 cancel을 막는다.

#### `_submit_risk_sell`, `_get_open_risk_order`, `_reconcile_risk_event`, `_process_risk_retry`

- risk 주문 생성 시 formal fields를 생성자에서 채우고, submit 전 local ID와 빈 broker ID를 저장한다.
- 제출 직후 pending snapshot에서 정확히 하나의 별도 broker `order_no`를 찾은 경우에만 OrderManager의 명시적 bind API를 호출한다. 없음/예외/복수/불일치/local ID 반환은 manual이고 추가 place/cancel은 0회다.
- `_get_open_risk_order`는 symbol만으로 추정하지 말고 `purpose == RISK_STOP`, SELL, open status, event/local/broker 관계를 확인한다. 동일 event 복수 주문은 `None`/manual로 처리한다.
- `CANCEL_REQUESTED` pending이 계속 보이면 기존 주문과 부분체결 잔량을 보존하고 cancel/place를 추가하지 않는다.
- pending에서 사라진 것만으로 즉시 retry하지 않는다. confirmation timeout 전에는 `CANCEL_REQUESTED`를 유지한다. timeout 후 broker 대조 실패/모호성은 manual로 종료하고 place 0회다. terminal 확정과 현재 보유 잔량이 확인된 경우에만 기존 retry 정책에 따라 `RETRY_PENDING`/risk-only 재주문을 허용한다.
- 재주문 수량은 음수가 아닌 현재 보유 잔량 및 broker 확인 잔량의 유효한 작은 값이며 0이면 `CLOSED`로 기록한다. 일반 `pending_resell`/일반 매도 retry를 호출하지 않는다.

#### `sync_pending_orders`, `_restore_risk_events`, `on_fill`

- pending risk event의 broker ID와 일치하는 주문을 기존 local ID로 복구하고 동일 pending을 반복 sync해도 중복 register하지 않는다.
- partial pending의 `filled_qty`/`unfilled_qty`와 order status를 보존한다.
- fill callback은 broker ID를 local ID로 덮어쓰지 않고 명확한 mapping 후에만 `apply_fill`한다. cumulative/동일 callback은 delta만 반영한다. partial은 event `SELL_PARTIAL`과 잔량을, full/position zero는 terminal 상태를 기록한다.
- 재시작 시 position zero는 추가 주문 없이 `CLOSED`; local/broker ID 누락, pending/account 조회 예외, symbol/side 다중 후보는 manual이다.

### 3.4 테스트 파일

- `tests/test_risk_sell_state_machine.py`: 기존 fake broker의 `place_order` local ID와 pending의 별도 `order_no`를 분리하고, pending을 submit 직후 제공하도록 수정한다. timeout cancel, pending 지속, confirmation timeout disappearance, cancel failure/exception, retry 0건, partial/duplicate fill을 보강한다.
- `tests/test_risk_restart_reconcile.py` (신규): `SQLiteStore(tmp_path)`에 durable event를 만든 뒤 새 `TradingEngine`을 생성한다. 별도 local/broker ID pending 복구, 반복 sync 중복 방지, partial 40/100→unfilled 60, position zero close, `CANCEL_REQUESTED` timeout 전 disappearance 재주문 0건과 timeout 후 manual, pending/account exception 및 missing/ambiguous identity를 검증한다.
- 기존 `tests/test_risk_event_recovery.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_guard.py`는 유지하며 formal field 추가로 깨지는 positional fixture만 명시적 keyword 또는 새 필드 계약에 맞게 최소 조정한다.

`broker/kiwoom_broker.py`, `broker/kiwoom_stub.py` 등 broker transport 파일은 수정하지 않는다. `main_live.py`, `infra/sqlite_store.py`, 전략 파일, `.opencode/`, 자동화/무관 문서는 이번 TASK-006에서 수정하지 않는다.

## 4. 불변조건 및 안전 제약

1. local ID와 broker ID는 항상 서로 다른 namespace로 보존한다. broker ID 미확정 시 cancel/place를 호출하지 않는다.
2. 동일 risk event의 open SELL은 최대 하나다. `CANCEL_REQUESTED` confirmation 전 `place_order` 호출은 0회다.
3. cancel API 성공은 취소 체결/확정이 아니다. pending 부재만으로 confirmation을 확정하지 않는다.
4. pending 조회 예외, 빈/모호한 identity, storage failure는 성공이나 빈 결과로 축약하지 않고 manual fail-closed한다.
5. 부분체결 및 누적 chejan은 delta만 portfolio, PnL, order/event에 반영한다.
6. `MANUAL_INTERVENTION_REQUIRED`, `SELL_FILLED`, `CLOSED`는 자동 retry하지 않는다.
7. risk 경로는 일반 매도 timeout/cancel/retry 및 `pending_resell`로 우회하지 않는다.
8. broker transport와 기존 전략/조건검색/실계좌 안전설정은 변경하지 않는다.

## 5. Acceptance tests

1. fake broker가 local `ORD_LOCAL_1`, pending broker `KR_BROKER_77`을 제공하면 Order/event에는 각각 다른 값이 저장되고 timeout cancel에는 `KR_BROKER_77`만 전달된다.
2. timeout cancel 성공 직후 state가 `CANCEL_REQUESTED`이고 registry/mapping이 유지된다. pending이 계속 있으면 추가 cancel/place는 0회다.
3. `CANCEL_REQUESTED` 주문이 pending에서 사라져도 confirmation timeout 전에는 state 유지 및 place 0회다.
4. confirmation timeout 후 broker 대조 실패/예외/모호성이면 `MANUAL_INTERVENTION_REQUIRED`이고 이후 tick/heartbeat에도 place 0회다.
5. submit 후 broker ID가 없음/예외/복수 후보/local ID이면 local ID를 broker ID로 복사하지 않고 manual이며 추가 주문 0회다.
6. 동일 pending risk order를 재시작 후 두 번 sync해도 주문 등록은 한 번이고 local/broker mapping은 정확히 하나다.
7. pending 40 filled / 60 unfilled / 100 total은 `PARTIAL` 및 잔량 60으로 복구되며 추가 place/cancel은 0회다.
8. 동일 cumulative fill callback을 두 번 보내도 portfolio 수량, realized PnL, filled quantity가 한 번만 감소/증가하고 partial event가 중복 갱신되지 않는다. full fill은 terminal이다.
9. 재시작 후 position zero, event ID 누락, local/broker ID 누락, broker pending/account 조회 exception, 동일 symbol의 복수 SELL 후보는 각각 close/manual fail-closed이며 자동 주문은 0회다.
10. 기존 RiskGuard 우선순위 및 일반 주문 회귀 테스트가 통과한다.
11. 전체 `python -m pytest -q`, Python 3.8 compile check, `git diff --check`가 통과한다.

## 6. 검증 명령

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/models.py','core/order_manager.py','engine.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

실계좌, 키움 COM, `main_live.py` live 실행, 실제 sleep/os._exit는 사용하지 않는다. 테스트 보고서에는 신규/수정 테스트 수와 각 failure-path의 주문·cancel 호출 횟수를 기록한다.

## 7. 롤백 고려사항

- 배포 전 SQLite를 백업한다. 이번 범위에는 schema migration이 없으므로 기존 risk event/order/fill/trade를 삭제하지 않는다.
- 롤백 대상은 `engine.py` risk cancel/reconcile/binding 변경, `core/models.py` additive fields, `core/order_manager.py` explicit mapping helper, 관련 테스트로 한정한다. broker transport와 unrelated 문서는 롤백 대상으로 삼지 않는다.
- 이미 broker에 제출된 주문은 코드 롤백 시 취소·재전송하지 않는다. broker pending, 계좌 잔량, local↔broker ID를 먼저 대조하고 불명확하면 수동 처리한다.
- 구버전 프로세스가 local ID를 broker ID로 오인할 수 있으므로 롤백/재시작 시 자동매매를 단일 프로세스로 중지하고 상태를 확인한다.
