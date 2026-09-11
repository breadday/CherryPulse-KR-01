# TASK-003 구현 명세 — 손절 주문 전용 상태 머신과 실패 경로 복구

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: 로컬 소스 현재 상태 및 TASK-001/TASK-002 검토 결과 (2026-09-10)

## 1. 목표와 범위

보유 포지션의 손절 주문을 일반 익절/재매도 경로에서 완전히 분리한다. 손절은 유효한 실시간 가격 틱에서 전략·뉴스·일봉·일반 매도 시간 게이트와 독립적으로 감지하되, 주문 제출 이후에는 손절 전용의 유한 상태 머신으로 timeout, 취소, 잔량 재주문, 부분체결, 거부, 예외, 프로세스 재시작, stale/reconnect 및 장마감 감시를 처리한다.

이번 작업은 주문 경로의 신뢰성/복구에 한정한다.

- 기존 전략별 손절률, 진입 조건, 익절/부분익절/trailing 조건은 변경하지 않는다.
- 손절 주문은 일반 `_submit_auto_sell`와 `pending_resell`를 공유하지 않는다.
- 실제 키움 계좌나 `RUN_MODE=live`를 실행하지 않는다. 모든 테스트는 fake broker와 임시 SQLite를 사용한다.
- 주문이 실제로 체결되었다고 로그만으로 추정하지 않는다. 체결 callback 또는 계좌/미체결 대조 결과만 상태 전이의 근거로 사용한다.

## 2. 현재 동작과 확인된 문제

### 2.0 현재 작업 트리와 증거 범위

이 명세를 작성할 때 `git status --short --branch`는 다음과 같았다.

- 브랜치: `automation/opencode-herdr-pipeline` (원격 `origin/automation/opencode-herdr-pipeline` 추적)
- 수정됨: `core/risk_manager.py`, `engine.py`, `infra/sqlite_store.py`
- 추적되지 않음: `core/risk_guard.py`, `tests/`, TASK-001/TASK-002 handoff 문서 및 로그, 이 문서

위 변경은 TASK-001/TASK-002의 기존 미커밋 산출물로 취급한다. 구현자는 이를 되돌리거나
정리하지 말고, 자신의 변경과 분리해 검토해야 한다. 현재 테스트 트리에는
`test_risk_guard.py`, `test_engine_risk_priority.py`, `test_risk_event_recovery.py`만
있으며, 이들은 입력 판정/우선순위/기본 SQLite idempotency만 증명한다. 실제 키움 COM,
`RUN_MODE=live`, 계좌번호·비밀값은 이 분석에서 읽거나 실행하지 않았다.

### 2.1 손절 감지/제출

- `engine.py:1996-2020`의 `TradingEngine.on_real_tick`은 유효 가격 후 `_check_risk_guard`를 외부 점수·일봉 캐시·전략보다 먼저 호출한다. 이 우선순위와 유효 틱이 없으면 주문하지 않는 원칙은 유지한다.
- `engine.py:2092-2130`의 `_check_risk_guard`는 열린 매도 주문이 있으면 중복을 막고, SQLite `risk_events`에 `STOP_DETECTED`를 만든다.
- `engine.py:2132-2172`의 `_submit_risk_sell`은 일반 자동매도 시간 게이트 없이 시장가 매도를 제출하지만, 현재는 제출 직후 `SELL_SUBMITTING`만 기록하고 risk 주문을 일반 미체결 관리와 구별할 수 있는 명시적 order metadata가 부족하다.

### 2.2 일반 매도 경로와 섞이는 문제

- `engine.py:1971-1989`의 `manage_pending_orders`는 모든 열린 주문 및 `pending_resell`를 `_check_stale_sell_order`/`_retry_sell_after_cancel`로 보낸다.
- `engine.py:2709-2801`의 `_check_stale_sell_order`는 risk 주문 여부를 검사하지 않고, 취소 요청 성공을 즉시 `CANCELED`로 확정하며 주문을 registry에서 제거한다.
- `engine.py:2806-2914`의 `_retry_sell_after_cancel`는 일반 `_auto_sell_allowed_now` 시간 게이트를 적용하고, `pending_resell`/`resell_retry_count`를 사용한다. 따라서 손절 잔량이 일반 재매도에 섞이거나, 15:20 이후 재주문이 차단될 수 있다.
- 현재 취소 실패는 `cancel_in_progress`만 해제하고 risk event를 수동개입 상태로 만들지 않는다. 재시작 시에도 해당 실패 원인을 durable state로 복원할 수 없다.

### 2.3 체결/복구/운영 문제

- `engine.py:3249-3367`의 `on_fill`은 risk event를 `SELL_PARTIAL`/`SELL_FILLED`로 갱신할 수 있으나, risk order의 timeout·취소·재주문 횟수와 연결된 전용 상태 처리가 없다.
- `engine.py:1840-1861`의 `_restore_risk_events`는 열린 event를 읽고 포지션이 0이면 `CLOSED`로 바꾸거나 local order id를 메모리에 복원할 뿐, broker 미체결 결과와 대조해 동일 주문을 보존하거나 유한 재시도/수동개입을 결정하지 않는다.
- `main_live.py:631-766`은 reconnect를 14:40 이후 보류하고, `main_live.py:1031-1072`는 stale 검사를 15:20 이후 중지한다. `main_live.py:959-1001`의 종료 흐름은 15:35에 프로세스를 종료한다. 즉 장마감 구간에 risk event가 남아도 감시/알림/복구 완료 여부를 검증할 전용 경로가 없다.
- TASK-001 review(`docs/agent-handoff/TASK-001-REVIEW.md:10-12`)도 risk-specific timeout/cancel/retry, restart reconciliation, late-session 검증 부재를 명시한다.

### 2.4 구현 시 우선순위가 필요한 최소 갭

1. **식별/영속성**: `Order`와 `orders.raw_payload`에 risk 목적 및 event id를 보존하고,
   `OrderManager`가 local id와 broker id를 유지한 채 risk open order를 별도로 찾도록 한다.
2. **상태 저장**: `risk_events`에 cancel/last-action/retry 정보를 additive migration으로
   추가하고, 모든 상태 전이를 한 DB transaction에서 기록한다. storage 오류는 재주문이
   아니라 fail-closed 수동개입이어야 한다.
3. **전용 dispatcher**: 일반 stale/cancel/retry 함수의 첫 분기에서 risk 주문을 분리하고,
   `CANCEL_REQUESTED`가 broker 조회로 확인되기 전에는 주문 registry 삭제나 재주문을 하지
   않는다. risk 경로에서 일반 시간 게이트와 `pending_resell`를 호출하지 않는다.
4. **broker 대조**: `sync_pending_orders`가 만든 generic `RESTORE_*` 주문을 durable risk
   event와 symbol/side/local/broker id로 연결한다. pending 조회가 실패하거나 결과가
   모호하면 빈 목록으로 복구 성공 처리하지 않는다.
5. **운영 경계**: `main_live`의 기존 reconnect/stale/shutdown 시각 정책은 유지하되,
   heartbeat와 종료 직전에 risk event 상태를 관찰·기록한다. stale 가격으로 새 STOP을
   만들지 않는다.

이 순서가 최소 범위다. 전략 조건, 포트폴리오 손익 계산, 일반 매도 정책을 동시에
개편하면 실패 원인과 롤백 단위가 섞이므로 금지한다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `core/risk_guard.py`

기존 `RiskPosition`, `RiskDecision`, `RiskGuard.check_stop`, `should_submit`의 판정 의미는 보존한다. 필요한 경우 다음 전용 상수/순수 helper를 추가한다.

- 허용 상태 집합과 terminal 상태(`SELL_FILLED`, `CLOSED`, `MANUAL_INTERVENTION_REQUIRED`)를 한 곳에서 정의한다.
- 동일 `symbol + position_key + stop` event에 대해 열린 event 또는 열린 risk 매도 주문이 있으면 `should_submit`이 계속 `False`여야 한다.
- `MANUAL_INTERVENTION_REQUIRED` 및 `CLOSED`는 자동 재주문 대상이 아니다.
- `restore_pending`은 조회 adapter 실패를 빈 성공 결과로 위장하지 않는다. 호출자가 storage failure와 no event를 구분할 수 있도록 예외 또는 명시적 실패 결과를 사용한다.

손절 가격 경계 `pnl <= stop_loss_pct`, invalid input 판정, qty/price 양수 조건은 절대 변경하지 않는다.

### 3.2 `core/models.py`

필요한 최소 범위에서 `Order`에 risk 주문임을 식별하는 metadata를 추가한다(예: `route`/`purpose`/`risk_event_id`). 기존 생성 호출과 직렬화가 깨지지 않도록 기본값을 둔다.

- risk 주문은 `purpose == "RISK_STOP"`와 durable `risk_event_id`를 가진다.
- 일반 매도는 기존 의미를 유지하고 risk metadata를 갖지 않는다.
- broker order number와 local order id를 혼동하지 않는다.

### 3.3 `core/order_manager.py`

다음 helper를 추가하거나 동등한 책임을 구현한다.

- `get_open_risk_sell_order_by_symbol(symbol)` 또는 risk event id 기준 조회.
- local id ↔ broker id 매핑을 유지한 채 risk order를 cancel/reconcile 대상에서 식별.
- 부분체결 이후 남은 수량은 `order.qty - order.filled_qty` 및 broker 보고 `unfilled_qty` 중 안전한 값으로 계산한다.

기존 일반 `exists_open_order`, 일반 매도 조회, 누적 체결 정규화의 동작은 회귀시키지 않는다. 열린 risk 매도는 일반 신규매수의 중복 방지에는 포함하되, 일반 매도 재시도 함수의 대상에는 포함하지 않는다.

### 3.4 `infra/sqlite_store.py`

기존 additive `risk_events` schema를 유지하고, 상태 머신에 필요한 최소 durable 정보를 확장한다. 기존 DB를 삭제/재작성하지 않는다.

- 필요한 경우 `cancel_requested_at`, `last_action_at`, `retry_count` 같은 컬럼을 `_ensure_column`으로 추가한다. 이미 `attempt_count`가 있으므로 동일 의미의 중복 컬럼을 만들지 않는다.
- `create_risk_event`는 unique idempotency 충돌 시 기존 event를 반환한다.
- `update_risk_event`는 state, local/broker order id, attempt count, retry/cancel timestamp, last error, qty, raw payload를 원자적으로 갱신한다.
- `get_open_risk_events`는 `SELL_FILLED`, `CLOSED`뿐 아니라 `MANUAL_INTERVENTION_REQUIRED`도 자동처리 목록에서 제외하거나, 명시적 `include_manual=True`로만 조회한다.
- `get_risk_event_by_idempotency_key`, event id 조회는 restart reconciliation의 유일한 durable source로 사용할 수 있어야 한다.
- DB 오류는 `MANUAL_INTERVENTION_REQUIRED` 전환 실패로 조용히 삼키지 말고, 엔진이 broker 주문을 추가로 반복하지 않도록 fail-closed 한다.

### 3.5 `engine.py`

핵심 변경 파일이다. 다음 심볼을 추가/변경한다.

#### A. 전용 상태와 설정

- `TradingEngine.__init__`에 `risk_order_context`/`risk_order_events`와 event별 `risk_retry_count`, `risk_cancel_in_progress`를 둔다. `pending_resell`, `resell_retry_count`, `cancel_in_progress`와 분리한다.
- `_load_runtime_config` 또는 동등한 설정 로더에서 다음 값을 읽는다. 기본값은 기존 일반 매도 timeout/retry보다 안전한 현재 설정을 재사용할 수 있으나, risk 값은 독립 key로 override 가능해야 한다.
  - `RISK_SELL_ORDER_TIMEOUT_SEC` (유한 양수)
  - `RISK_SELL_RETRY_DELAY_SEC` (유한 0 이상)
  - `RISK_SELL_MAX_RETRY_COUNT` (유한 정수, 0 이상)
  - `RISK_CANCEL_CONFIRM_TIMEOUT_SEC` (유한 양수)
  - `RISK_RECONCILE_INTERVAL_SEC` (유한 양수)

잘못된 설정은 무한 재시도/무한 대기가 아니라 보수적인 유한 기본값으로 정규화한다.

#### B. 손절 제출 및 상태 갱신

- `_submit_risk_sell(symbol, qty, reason, risk_event_id, idempotency_key)`는 `Signal(..., Side.SELL, OrderType.MARKET)`를 생성하고 risk metadata를 부착한다.
- 제출 전에 현재 보유수량과 risk event/open risk order를 다시 확인한다. qty는 요청량과 현재 보유량 중 작은 값이다.
- `broker.place_order` 예외 또는 `REJECTED`는 event를 `MANUAL_INTERVENTION_REQUIRED`로 전환하고 추가 자동주문을 금지한다. Telegram/log에는 event id, key, symbol, qty, state, reason, error를 포함한다.
- 저장 성공 전에는 제출 성공 상태를 확정하지 않는다. 저장소 장애로 event의 local id/attempt를 기록할 수 없으면 동일 주문 재전송을 시도하지 않고 수동개입으로 끝낸다.
- 성공 주문은 `SELL_SUBMITTING` 또는 `SELL_WORKING`으로 저장하고 local id, broker id(알 수 있을 때), attempt count를 기록한다. 제출 API의 반환 성공은 체결 성공이 아니다.
- 손절 경로에서는 `_auto_sell_allowed_now`, `pending_resell`, 일반 retry counter, grace, trend-hold를 호출하지 않는다.

#### C. risk 전용 timeout/cancel/reorder

- `_check_stale_sell_order`는 먼저 risk metadata/event를 확인한다. risk 주문이면 `_check_stale_risk_order`로만 위임하고 일반 주문 처리는 건너뛴다.
- `_check_stale_risk_order`는 유효한 열린 risk order의 남은 수량이 timeout을 넘었을 때 한 번만 cancel request를 보낸다. `cancel_order`의 return 0은 “취소 요청 접수”로 기록할 뿐, broker 확인 전 최종 취소/재주문으로 간주하지 않는다.
- cancel request는 `CANCEL_REQUESTED`와 timestamp로 저장한다. broker pending/체결 대조에서 취소가 확인된 뒤에만 `CANCELED`/`RETRY_PENDING`으로 전이한다.
- 부분체결이 먼저 오면 `SELL_PARTIAL`로 저장하고, 이후 cancel/reorder 수량은 잔량만 사용한다. 중복/누적 chejan은 기존 `_normalize_fill_qty`로 0 수량 처리한다.
- 취소 확인 후 delay가 지나고 잔량이 남으면 risk 전용 재주문을 한다. 재주문은 `RISK_SELL_MAX_RETRY_COUNT`를 초과하지 않는다. 재주문 시 새 local order id를 만들고 parent risk event/idempotency key는 유지한다.
- cancel 실패, cancel confirmation timeout, risk 재주문 reject/exception, 최대 횟수 초과는 `MANUAL_INTERVENTION_REQUIRED`로 terminal 처리한다. 이 상태에서는 새 sell을 자동 제출하지 않는다.
- 일반 매도의 timeout/cancel/retry와 risk 매도의 counters, flags, logs, state를 절대로 공유하지 않는다.

#### D. `manage_pending_orders`와 체결

- `manage_pending_orders`는 일반 order와 risk order를 분류해 각각의 handler를 호출한다.
- risk event가 terminal이거나 포지션 잔량이 0이면 해당 메모리 상태를 정리하되 durable event는 `SELL_FILLED` 또는 `CLOSED`로 보존한다.
- `on_fill`에서 risk event를 찾아 부분/완전 체결 state와 잔량을 원자적으로 기록한다. 부분체결은 `sell_in_progress`를 풀더라도 risk event가 열려 있는 동안 일반 `_submit_auto_sell`/`pending_resell`로 우회하지 않는다.
- risk 주문의 `reason`/event id를 trade exit reason에 보존한다. 기존 일반 매도 손익 집계와 중복 기록하지 않는다.

#### E. 재시작 복구

- `sync_account` 및 `sync_pending_orders`가 끝난 뒤 `_restore_risk_events`를 호출한다.
- 각 열린 event에 대해 현재 포지션 잔량과 broker pending orders를 event의 broker/local id, symbol, SELL side로 대조한다.
  1. 잔량 0: 추가 주문 없이 `CLOSED`.
  2. 동일 risk broker order가 pending/partial: local mapping과 context를 복구하고 `SELL_SUBMITTING`/`SELL_PARTIAL` 유지. 재전송하지 않음.
  3. event가 `CANCEL_REQUESTED`: cancel confirmation/reconcile 전에는 재전송하지 않음.
  4. broker 상태가 확정적으로 terminal이고 잔량이 남으며 retry budget이 남음: `RETRY_PENDING`으로 복구 후 delay 뒤 risk-only 재주문.
  5. 제출 결과가 불명확하거나 DB/broker 대조가 실패함: `MANUAL_INTERVENTION_REQUIRED`, 자동 재주문 금지.
- 복구는 동일 idempotency key로 event를 새로 만들지 않는다. 기존 broker order가 있으면 새 주문 수는 0이어야 한다.

### 3.6 `main_live.py`

`main_live.py`는 연결/장시간 책임만 유지하며 가격을 추정해 손절하지 않는다.

- `_all_watch_codes`/`_should_route_tick`에서 보유종목과 열린 risk order가 snapshot에 없어도 계속 라우팅되는 기존 보존을 확인한다.
- `on_heartbeat` 또는 별도 timer에서 `engine.manage_pending_orders`/risk reconciliation을 장중 stale 복구와 독립적으로 계속 호출한다. stale tick이 없을 때는 새 risk 매도 주문을 만들지 않고, 열린 event의 상태 확인/알림/수동개입 전환만 수행한다.
- 14:40 이후 reconnect 보류, 15:20 이후 stale recovery 중지, 15:35 자동종료 정책 자체는 임의로 완화하지 않는다. 다만 종료 시 열린 risk event, cancel pending, manual intervention 상태를 로그/Telegram으로 남기고 `os._exit` 전에 마지막 계좌·미체결 대조를 시도한다.
- reconnect 성공 후 `sync_account → sync_pending_orders → health_check` 순서로 risk event 복구가 실행되는지 보장한다. reconnect 실패/장마감 복구 보류는 주문 성공으로 기록하지 않는다.

### 3.7 `broker/kiwoom_broker.py` 및 `broker/kiwoom_stub.py`

가능하면 기존 `place_order`/`cancel_order` transport API는 유지한다. 구현상 취소 확인 또는 broker order metadata가 필요하면 최소 변경으로 다음만 추가한다.

- pending order 조회 결과에 risk 식별을 transport가 임의로 추정하지 말고 engine의 local/broker mapping으로 연결한다.
- `_send_order_with_retry`의 제한된 API 재시도와 engine-level cancel/reorder를 구분한다. transport retry를 무한히 늘리거나 risk 주문을 일반 매도 재주문으로 바꾸지 않는다.
- fake/stub은 호출 기록, 반환값, pending 목록, partial fill, reject, timeout, reconnect를 주입할 수 있어야 한다.

실제 키움 COM 호출을 테스트에서 실행하지 않는다.

### 3.8 테스트 파일

기존 `tests/test_risk_guard.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_event_recovery.py`는 유지·확장하고 다음 파일을 추가한다.

- `tests/test_risk_sell_state_machine.py`: timeout/cancel/재주문/부분체결/거부/예외/횟수 초과.
- `tests/test_risk_restart_reconcile.py`: 새 engine + 기존 SQLite + fake broker pending/position 조합.
- `tests/test_risk_late_session.py`: stale, reconnect blocked, 장마감 종료 경계.

테스트는 실제 시간 sleep 대신 clock/time monkeypatch를 사용한다.

## 4. 상태 머신 계약

정상 흐름:

```text
STOP_DETECTED
  -> SELL_SUBMITTING (risk order accepted by broker API, not filled)
  -> SELL_PARTIAL    (partial fill, remain > 0)
  -> SELL_FILLED     (fill confirms remain == 0)
  -> CLOSED          (position/account reconciliation confirms qty == 0)
```

timeout 흐름:

```text
SELL_SUBMITTING/SELL_PARTIAL
  -> CANCEL_REQUESTED
  -> RETRY_PENDING       (cancel confirmed, remain > 0, retry budget remains)
  -> SELL_SUBMITTING     (new risk-only order)
  -> MANUAL_INTERVENTION_REQUIRED (cancel failure/unknown/limit/reject/storage failure)
```

규칙:

1. `SELL_FILLED`, `CLOSED`, `MANUAL_INTERVENTION_REQUIRED`는 terminal 자동 처리 상태다.
2. `CANCEL_REQUESTED`에서 cancel 확인 전 새 매도를 제출하지 않는다.
3. 모든 retry에는 delay와 최대 횟수가 있고, retry count는 프로세스 메모리가 아닌 SQLite에 보존한다.
4. 동일 event에 동시에 열린 risk sell은 최대 1개다.
5. 수량은 항상 현재 계좌 잔량과 broker 미체결 잔량 중 보수적으로 작은 값이다.
6. stale 데이터만으로 가격 기반 `STOP_DETECTED`를 만들지 않는다. stale는 열린 주문 감시/수동개입 알림의 사유일 뿐이다.

## 5. 불변조건과 안전 제약

1. `RUN_MODE=live`를 켜지 않고, 계좌번호/비밀번호/token/.env를 읽거나 출력하지 않는다.
2. 실제 broker에 제출된 주문은 체결 callback/계좌 조회 전까지 미체결로 취급한다.
3. 손절 감지는 유효한 실제 틱에서만 수행하며, 일반 매도 시간 게이트·전략 보호·뉴스·일봉·grace·trend-hold·stale flag가 이를 막지 않는다.
4. 유효 틱이 없으면 자동 손절 주문을 추정하지 않는다. 장마감에도 열린 risk event 감시는 유지하되 새 가격 주문은 만들지 않는다.
5. 일반 `pending_resell`, `resell_retry_count`, 일반 cancel flag를 risk state에 사용하지 않는다.
6. 부분체결/중복 chejan은 포지션과 realized PnL을 중복 반영하지 않는다.
7. SQLite/broker 대조 실패, 취소 확인 timeout, 주문 거부/예외, retry 한도 초과는 자동 성공으로 포장하지 않고 `MANUAL_INTERVENTION_REQUIRED`로 남긴다.
8. 기존 일반 매도, 신규매수 리스크 한도, 보유종목 감시, 당일 손절 후 재진입 차단은 회귀하지 않는다.
9. QEventLoop, broker TR, reconnect, cancel confirmation에는 모두 timeout과 유한 재시도/백오프가 있다.
10. 로그/DB/Telegram 이벤트에는 최소 `risk_event_id`, `idempotency_key`, `symbol`, `qty`, `state`, `reason`, `attempt_count`를 포함한다. 비밀값은 포함하지 않는다.

## 6. Acceptance tests

### 정상 경로

1. 손절 경계값에서 `STOP_DETECTED`가 한 번 생성되고 risk 시장가 주문 1건만 제출된다. 일반 auto-sell 시간 밖에서도 제출된다.
2. 제출 성공 후 event가 `SELL_SUBMITTING`/`SELL_WORKING`으로 저장되고, broker fill 없이 체결로 표시되지 않는다.
3. 부분체결 40/100 후 `SELL_PARTIAL`, event/portfolio 잔량 60이 저장되고, 후속 timeout/cancel/reorder는 60주만 대상으로 한다.
4. 잔량 60의 cancel confirmation 후 risk-only 재주문 60주가 제출되고 attempt count가 증가한다. 일반 `_retry_sell_after_cancel` 호출 및 일반 시간 게이트 호출은 0회다.
5. 잔량이 0인 fill 후 `SELL_FILLED` 또는 계좌 대조 후 `CLOSED`가 되고 동일 틱/후속 틱에서 추가 주문이 없다.
6. 일반 자동매도 주문은 기존 `_auto_sell_allowed_now` 및 `pending_resell` 정책을 그대로 따른다.

### 실패/경계 경로

1. broker `place_order`가 `REJECTED`를 반환하면 risk event가 `MANUAL_INTERVENTION_REQUIRED`이고 risk broker 호출은 추가로 발생하지 않는다.
2. broker `place_order`가 예외를 내거나 SQLite event update가 실패하면 자동 재주문 없이 수동개입 로그/알림이 남는다.
3. timeout 시 cancel 호출은 한 번만 발생한다. cancel 실패/예외이면 즉시 또는 confirmation timeout 후 수동개입 상태가 되고 무한 cancel loop가 없다.
4. cancel return 0 뒤 broker pending에 주문이 계속 있으면 새 주문을 내지 않는다. pending에서 사라지고 잔량이 남는 것이 확인된 뒤에만 retry한다.
5. retry count가 최대치에 도달하면 `MANUAL_INTERVENTION_REQUIRED`가 되고 이후 heartbeat/tick에서도 주문 수가 증가하지 않는다.
6. 동일 risk event에 같은 틀/중복 fill callback을 반복해도 portfolio qty, realized PnL, DB fill 결과가 중복 감소/증가하지 않는다.
7. 동일 symbol의 일반 매도와 risk 매도가 동시에 존재할 때 risk handler는 risk order만 다루고 일반 retry handler는 risk order를 건너뛴다.
8. 재시작 fixture에서 `SELL_SUBMITTING`/`SELL_PARTIAL`과 동일 broker pending order가 있으면 새 order 0건, mapping/context 복원, 잔량 유지가 확인된다.
9. 재시작 시 포지션 잔량이 0이면 risk event를 `CLOSED`로 종료하고 broker 호출 0건이다.
10. 재시작 시 event는 열려 있지만 broker/DB 대조가 실패하거나 제출 결과가 불명확하면 `MANUAL_INTERVENTION_REQUIRED`이며 자동 재전송하지 않는다.
11. stale heartbeat와 reconnect blocked를 주입해도 마지막으로 수신한 유효 틱의 손절은 제출된다. 반대로 유효 틱을 전혀 주지 않으면 stale 가격으로 주문하지 않고 열린 event/수동개입 상태만 기록한다.
12. 14:40 이후 reconnect 보류, 15:20 이후 stale recovery 중지, 15:35 shutdown 경계에서 열린 risk event가 조용히 삭제되지 않고 마지막 상태/잔량/수동확인 필요 로그가 남는다.
13. invalid price/avg/qty/stop(`None`, 0, 음수, 문자열, NaN, infinity)은 `INVALID_INPUT`, broker 호출 0건이다.
14. 기존 관련 테스트와 일반 매도 회귀 테스트가 모두 통과하고, 조건검색/전략 활성 상태가 변경되지 않는다.

### 검증 명령

구현자는 `.venv`가 Python 3.8이면 이를 우선 사용하고, 아래 결과를 구현 보고서에 원문으로 기록한다. live 실행/키움 COM 연결 명령은 실행하지 않는다.

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/models.py','core/risk_guard.py','core/order_manager.py','engine.py','broker/kiwoom_broker.py','broker/kiwoom_stub.py','main_live.py','config_live.py','infra/sqlite_store.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

전체 pytest가 실패하면 성공으로 포장하지 말고, 실패 테스트와 원인을 구분한다. 실제 주문/계좌 대조는 acceptance evidence가 아니다.

## 7. 롤백 고려사항

- 배포 전 SQLite 파일을 백업한다. schema 변경은 additive이며 기존 `risk_events`, orders, fills, trades를 삭제하지 않는다.
- 코드 롤백은 `engine.py`의 risk-specific dispatcher/state handler, `core/models.py` metadata, `core/order_manager.py` 조회 helper, `infra/sqlite_store.py` additive column/method 변경, config key 및 테스트를 단위별로 되돌릴 수 있어야 한다.
- 이미 broker에 제출된 risk 주문을 롤백 과정에서 취소하거나 재전송하지 않는다. 먼저 계좌 보유수량과 미체결 주문을 조회하고, event 감사 기록을 보존한 뒤 수동 대조한다.
- 새 상태를 이해하지 못하는 구버전 프로세스와 동시에 실행하지 않는다. 전환 중에는 신규 자동매매를 중지하고 단일 프로세스만 DB를 소유한다.
- 구현이 불완전하거나 storage/reconnect 대조가 실패하면 일반 재매도 경로로 우회하지 말고 `MANUAL_INTERVENTION_REQUIRED`와 수동 확인으로 중단한다.
- 설정 rollback 시 risk timeout/retry key가 없어도 유한 보수 기본값으로 동작해야 하며, 기존 일반 `SELL_ORDER_TIMEOUT_SEC`/`RETRY_SELL_*` 값을 손절 상태 머신의 무한 재시도 용도로 재해석하지 않는다.
