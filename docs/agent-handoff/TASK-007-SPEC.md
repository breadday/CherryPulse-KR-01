# TASK-007 구현 명세 — TASK-006 Review 미완성 항목만 구현

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-006-REVIEW.md` 및 현재 작업 트리 (2026-09-10)

## 1. 목표와 범위

TASK-006 Review에서 승인되지 않은 주문 identity/type 계약만 보완한다. 목표는 다음과 같다.

1. `Order`에 risk 목적, risk event, broker 주문번호를 정식 dataclass 필드로 둔다.
2. `OrderManager`가 local ID와 broker ID를 양방향으로 명시적·일관되게 연결하고, 불명확한 연결은 거부한다.
3. `engine.py`의 risk submit/reconcile/restart/fill/cancel 경로가 그 API만 사용하도록 바꾼다.
4. 누락·충돌·복수 identity에서는 자동 `place_order`와 `cancel_order`가 모두 0회임을 fake broker 테스트로 증명한다.
5. 재시작, partial fill, duplicate/cumulative fill 및 조회 예외 failure-path 테스트를 추가한다.

이번 작업은 TASK-006 Review의 미완성 항목만 대상으로 한다. broker transport, `main_live.py`, SQLite schema, 전략/조건검색, 기존 live 안전 설정 및 무관한 작업 트리 변경은 수정하지 않는다.

## 2. 현재 동작과 근거

- `core/models.py:58-70`의 `Order`에는 `purpose`, `risk_event_id`, `broker_order_id`가 없다. 현재 `engine.py:2210-2214`, `1843-1844`, `2976-2978`에서 인스턴스에 동적으로 부착한다.
- `core/order_manager.py:10`은 broker→local dict만 보유하며, `:83-95`의 `bind_broker_order_id(symbol, broker_order_id)`는 symbol 기준 최근 open 주문을 추정한다. local ID를 명시적으로 받지 않고 risk event/context 및 다중 후보를 검증하지 않는다.
- `engine.py:2237`, `:1849`, `:2980`은 `broker_to_local_id`를 직접 갱신한다. `:2828-2835`의 일반 매도 cancel도 mapping을 순회한 뒤 local ID를 broker ID로 fallback한다.
- `engine.py:3496-3499`의 fill 처리는 `resolve_order_id`에 의존한다. 매핑되지 않은 fill도 `:3512`에서 portfolio에 먼저 반영할 수 있어, identity가 불명확한 체결이 상태를 오염시킬 수 있다.
- `engine.py:1800-1865`, `:2940-2994`는 pending/event 복구를 수행하지만 broker ID와 local ID를 정식 API로 검증하지 않으며, 동일 event 복수 주문 및 missing/ambiguous 조회 결과를 충분히 fail-closed하지 않는다.
- 현재 자동 테스트는 `tests/`의 risk 관련 8개뿐이고 `tests/test_risk_restart_reconcile.py`가 없다. TASK-006 Review는 restart, 40/100→60 partial, duplicate cumulative fill, 조회 예외, missing/ambiguous identity, 호출 0회를 미검증 항목으로 지적했다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `core/models.py` — `Order`

기존 positional 생성 호출을 깨지 않도록 기존 필수 필드 및 `ts`의 기본값 순서를 유지한 뒤 다음 additive 필드를 추가한다.

```python
purpose: str = ""
risk_event_id: str = ""
broker_order_id: str = ""
```

계약:

- `order_id`는 항상 내부 local ID이다.
- `broker_order_id`만 broker 주문번호이며, local ID를 fallback으로 복사하지 않는다.
- 일반 주문의 세 필드 기본값은 빈 문자열이다.
- risk stop 주문은 `purpose == "RISK_STOP"`이고 동일한 `risk_event_id`를 가진다.

### 3.2 `core/order_manager.py` — `OrderManager`

기존 `orders`, 일반 open 조회, `exists_open_order`, `apply_fill`의 동작은 유지한다. broker mapping은 외부에서 직접 수정하지 못하도록 하는 것이 이상적이며, 호환성을 위해 기존 `broker_to_local_id`를 남길 경우에도 모든 생산 코드 갱신은 아래 API를 거친다.

추가/보강할 API 계약:

- `bind_broker_order_id(local_order_id: str, broker_order_id: str, risk_event_id: str = "") -> Optional[Order]`
  - 두 ID가 모두 비어 있지 않고 서로 달라야 한다.
  - local order가 실제로 존재해야 한다.
  - `risk_event_id`가 전달되면 order가 risk stop이고 같은 event여야 한다. 전달된 event가 없더라도 이미 order의 risk event가 있으면 다른 event로 binding하지 않는다.
  - broker ID가 이미 다른 local order에 연결되어 있거나, local order가 다른 broker ID를 보유하면 거부한다.
  - 기존 mapping, reverse mapping, `Order.broker_order_id`가 서로 불일치하는 상태를 자동으로 추정/덮어쓰지 말고 거부한다.
  - 성공할 때만 `local_to_broker_id[local]`, `broker_to_local_id[broker]`, `order.broker_order_id`를 함께 기록하고 order를 반환한다.
  - 실패 시 mapping과 order를 변경하지 않고 `None`을 반환한다.

- `get_order_by_broker_id(broker_order_id: str) -> Optional[Order]`
  - 명시적 broker→local mapping과 대상 order의 `broker_order_id`가 모두 일치할 때만 반환한다.
  - 빈 ID, mapping 누락, local order 누락, reverse field 불일치, 복수 local 후보는 `None`이다.

- `get_open_risk_sell_order_by_event(event_id: str) -> Optional[Order]`
  - `event_id`가 비어 있지 않고, `purpose == "RISK_STOP"`, side SELL, `PENDING/SUBMITTED/PARTIAL`, 동일 risk event인 order만 후보로 삼는다.
  - 후보가 정확히 1개일 때만 반환하고 0개 또는 2개 이상이면 `None`으로 fail-closed한다.

필요하면 `get_broker_order_id(local_order_id)` 같은 read-only helper를 추가할 수 있으나, 반환값은 확정된 mapping/field가 일치할 때만 허용한다. 부분체결 잔량 helper를 추가하는 경우 음수·총량 초과·비정상 broker 수량은 거부하고, 유효할 때 `min(local_remaining, broker_unfilled)`를 사용하며 broker 값이 없을 때만 local 계산값을 사용한다.

### 3.3 `engine.py` — risk identity 경로

다음 심볼을 최소 변경한다.

- `_submit_risk_sell`
  - risk metadata를 formal `Order` 필드에 기록하고, submit 전 local ID와 빈 broker ID를 durable event에 보존한다.
  - submit 직후 pending snapshot에서 symbol/SELL 및 해당 주문의 risk context·수량에 맞는 broker order가 정확히 하나일 때만 `OrderManager.bind_broker_order_id(local, broker, event)`를 호출한다.
  - 0개, 복수, 조회 예외, broker ID가 local ID와 동일하거나 이미 다른 주문에 연결된 경우 binding 실패로 `MANUAL_INTERVENTION_REQUIRED`를 저장하고 이후 추가 place/cancel을 하지 않는다.
  - `broker_to_local_id[...] = ...` 직접 대입을 제거한다.

- `sync_pending_orders`, `_restore_risk_events`, `_reconcile_risk_event`
  - durable event의 local/broker ID와 pending/account 결과를 대조한다.
  - 기존 local order가 있으면 중복 register하지 않고, 없으면 formal risk fields를 가진 order를 한 번만 복구한 뒤 명시적 bind API를 사용한다.
  - 같은 broker pending을 두 번 sync해도 order 1개, 양방향 mapping 1개만 남겨야 한다.
  - partial pending의 total/filled/unfilled를 검증하여 `filled_qty`, `PARTIAL`, 잔량 60(예: total 100, filled 40, unfilled 60)을 보존한다. 추가 place/cancel은 하지 않는다.
  - event ID, local ID, broker ID가 누락되거나 symbol/side 후보가 복수이거나 pending/account 조회가 예외이면 성공/빈 결과로 축약하지 말고 manual 상태로 저장하며 자동 주문 0회를 보장한다.
  - `CANCEL_REQUESTED`가 pending에서 사라진 것만으로 terminal/cancel confirmation/retry를 확정하지 않는다. confirmation timeout 전에는 기존 order/mapping/state를 유지하고, timeout 후 broker/account 대조가 실패·예외·모호하면 manual 및 place 0회다. terminal과 보유 잔량이 모두 확인된 경우에만 기존 risk-only retry 정책을 허용한다.
  - `_get_open_risk_order`는 symbol 최근 주문 추정 대신 event 기준 manager query 및 formal fields 검증을 사용한다. 동일 event 복수 open SELL은 `None`/manual이다.

- `_check_stale_risk_order` 및 일반 `_check_stale_sell_order`
  - risk cancel은 확정된 `order.broker_order_id`/manager 조회값으로만 호출한다. 누락·불일치면 cancel 0회 및 manual이다.
  - cancel 반환 0/None은 `CANCEL_REQUESTED` 접수로만 기록한다. order, mapping, broker ID를 삭제하거나 `CANCELED`, `RETRY_PENDING`으로 바꾸지 않으며, 같은 event의 중복 cancel/place를 막는다.
  - 일반 매도 경로도 local ID를 broker ID로 fallback하지 않는다. 확정 broker ID가 없으면 cancel하지 않고 기존 일반 risk retry로 우회하지 않는다.

- `on_fill`, `_normalize_fill_qty`
  - fill의 broker ID를 `get_order_by_broker_id`로 먼저 해석하고 명확한 order일 때만 `apply_fill` 및 portfolio/PnL을 실행한다. 미매핑·불일치 fill은 상태/portfolio를 변경하지 않는다.
  - cumulative `unfilled_qty`를 이용해 delta만 반영한다. 같은 callback을 반복하면 delta 0, portfolio 수량·realized PnL·order filled_qty/event가 중복 증가하지 않는다.
  - partial은 `SELL_PARTIAL`과 잔량을, full 또는 position zero는 terminal(`SELL_FILLED`/`CLOSED`)을 저장하며 terminal event는 retry하지 않는다.
  - risk event 연결은 order의 formal `risk_event_id`와 확정 broker/local binding을 우선 사용하고, 임의 dict key 추정에 의존하지 않는다.

### 3.4 테스트

- `tests/test_risk_sell_state_machine.py`
  - fake broker의 local `ORD_LOCAL_1`과 pending broker `KR_BROKER_77`을 분리한다.
  - timeout cancel에 broker ID만 전달되는지, `CANCEL_REQUESTED`와 mapping/order가 유지되는지, pending 지속 및 confirmation timeout disappearance에서 추가 place/cancel이 0회인지 검증한다.
  - pending 없음/예외/복수/local-ID 후보, cancel 실패/예외의 manual fail-closed를 검증한다.
  - 40/100→60 partial 및 동일 cumulative fill 반복의 portfolio/PnL/order/event delta를 검증한다.

- `tests/test_risk_restart_reconcile.py` (신규)
  - `SQLiteStore(tmp_path)`에 durable event를 만든 뒤 새 `TradingEngine`을 생성한다.
  - 별도 local/broker ID 복구와 두 번의 sync 중복 방지, partial 상태/잔량 보존, position zero의 `CLOSED` 전이를 검증한다.
  - `CANCEL_REQUESTED` pending disappearance의 timeout 전 무재주문, timeout 후 manual, pending/account 예외, missing/ambiguous identity 각각에 대해 `place_calls == 0` 및 `cancel_calls == 0`을 검증한다.

기존 `tests/test_risk_event_recovery.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_guard.py`는 유지한다. positional `Order(...)` fixture 조정이 필요할 때만 keyword 또는 formal field에 맞춘 최소 수정으로 처리한다.

## 4. 불변조건 및 안전 제약

1. local ID와 broker ID는 다른 namespace로 보존하며 서로 복사하지 않는다.
2. identity가 missing, ambiguous, conflicting이면 자동 place/cancel은 각각 0회다.
3. 동일 risk event의 open SELL은 최대 하나이며, `CANCEL_REQUESTED` confirmation 전 재주문은 0회다.
4. cancel API 성공은 broker 취소 확정/체결이 아니다.
5. partial/누적/중복 fill은 delta만 portfolio, PnL, order/event에 반영한다.
6. `MANUAL_INTERVENTION_REQUIRED`, `SELL_FILLED`, `CLOSED`는 자동 retry하지 않는다.
7. risk path는 일반 매도 timeout/cancel/retry 및 `pending_resell`로 우회하지 않는다.
8. 조회/storage 예외를 빈 목록이나 성공으로 처리하지 않는다.
9. broker transport 파일과 `main_live.py`를 수정하지 않는다. 실 broker/COM/live 실행을 하지 않는다.

## 5. Acceptance tests

1. `Order`를 생성하면 세 필드가 존재하고 기본값이 빈 문자열이며, risk order에는 purpose/event가 보존된다.
2. local `ORD_LOCAL_1` ↔ broker `KR_BROKER_77` binding 성공 시 양방향 조회와 order field가 일치한다.
3. unknown local, 빈/동일 ID, broker 재사용, local의 다른 broker 재binding, event mismatch는 모두 binding 실패이며 기존 상태를 변경하지 않는다.
4. risk event open SELL 0개 또는 2개 이상은 manager query가 `None`을 반환한다.
5. timeout cancel에는 `KR_BROKER_77`만 전달되고 성공 직후 state는 `CANCEL_REQUESTED`이며 order/mapping이 남는다.
6. pending 지속, pending disappearance(confirmation timeout 전), confirmation timeout 후 대조 예외/모호성은 추가 place/cancel 0회이며 마지막 경우 manual이다.
7. submit 후 broker ID 없음/예외/복수/local ID는 local ID를 broker ID로 복사하지 않고 manual 및 추가 place/cancel 0회다.
8. restart 후 동일 pending 두 번 sync는 order 1개와 mapping 1개만 만들고, total 100/filled 40/unfilled 60은 PARTIAL 및 잔량 60으로 보존한다.
9. 동일 cumulative fill callback 두 번은 한 번의 delta만 반영한다. full fill/position zero는 terminal이고 retry하지 않는다.
10. pending/account query exception, event/local/broker ID 누락, symbol/side 복수 후보는 manual/closed 정책을 따르고 자동 주문 0회다.
11. 기존 risk priority 및 일반 주문 회귀 테스트가 통과한다.
12. 다음 검증이 통과한다.

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/models.py','core/order_manager.py','engine.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
```

테스트 보고서에는 신규/수정 테스트 수와 각 failure-path의 `place_order`/`cancel_order` 호출 횟수를 명시한다.

## 6. 롤백 고려사항

- 배포 전 SQLite를 백업한다. schema migration은 범위가 아니므로 기존 event/order/fill/trade를 삭제하거나 변환하지 않는다.
- 롤백 대상은 `core/models.py`의 additive fields, `core/order_manager.py` mapping/query API, `engine.py` identity/reconcile/fill/cancel 변경 및 관련 테스트로 한정한다. broker transport, `main_live.py`, 무관한 기존 작업 트리 변경은 건드리지 않는다.
- 이미 broker에 제출된 주문을 롤백 코드가 취소하거나 재전송하지 않도록 한다. broker pending, account position, durable event 및 local↔broker ID를 먼저 수동 대조한다.
- 구버전 프로세스가 local ID를 broker ID로 오인할 수 있으므로 롤백/재시작 시 자동매매를 단일 프로세스로 중지하고, identity가 확정될 때까지 자동 place/cancel을 차단한다.
