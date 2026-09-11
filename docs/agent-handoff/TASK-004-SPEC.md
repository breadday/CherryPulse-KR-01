# TASK-004 구현 명세 — TASK-003 Review 지적사항 보완

상태: `IMPLEMENTATION_CONTRACT` (구현 전 명세)
기준: `docs/agent-handoff/TASK-003-REVIEW.md` 및 현재 작업 트리 (2026-09-10)

## 1. 목표와 범위

TASK-003 Review의 지적사항만 보완한다. 손절(`RISK_STOP`) 주문의 취소 확인 timeout·취소·재주문을 일반 매도 경로와 완전히 분리하고, broker 미체결 대조, 프로세스 재시작 복구, stale/reconnect/장마감 감시를 fake broker 기반 테스트로 증명한다.

다음은 변경하지 않는다.

- 기존 Python 3.8 호환 수정과 `RiskGuard`의 기본 판정 동작(`pnl <= stop`, invalid input, 양수 price/avg/qty)을 유지한다.
- 전략 조건, stop-loss 설정값, 일반 매도 timeout/cancel/retry, 신규매수 RiskGuard 차단 동작을 변경하지 않는다.
- 실계좌, `RUN_MODE=live`, 키움 COM, 계좌번호·비밀값을 테스트에서 사용하지 않는다.
- TASK-003과 무관한 기존 변경사항을 되돌리거나 정리하지 않는다.

## 2. 현재 동작과 Review 근거

- `engine.py:621-625`에서 `RISK_CANCEL_CONFIRM_TIMEOUT_SEC`와 `RISK_RECONCILE_INTERVAL_SEC`를 읽지만 실제 처리에 사용하지 않는다.
- `engine.py:_check_stale_risk_order`는 timeout 후 `CANCEL_REQUESTED`를 기록할 뿐, confirmation timeout에서 `MANUAL_INTERVENTION_REQUIRED`로 전이하지 않는다. `sync_pending_orders`가 간접적으로 pending 부재를 처리한다.
- `engine.py:1799-1897`의 `sync_pending_orders`/`_restore_risk_events`는 broker pending 결과와 durable event의 symbol/side/local id/broker id 조합을 명시적으로 판정하지 않는다. 모호하거나 식별자가 없는 경우의 안전한 분기가 없다.
- risk metadata(`purpose`, `risk_event_id`, `broker_order_id`)가 `Order` dataclass의 정식 필드가 아니라 `engine.py`에서 동적으로 부착된다. `OrderManager`에도 risk 전용 조회 API가 없다.
- `main_live.py:1031-1072`의 `on_heartbeat`는 `market_session` 밖에서 즉시 반환하고, `15:20` 이후 stale 검사를 중지한다. `_recover_broker_session`은 `14:40` 이후 재접속을 보류한다.
- `main_live.py:959-1001`의 shutdown은 열린 risk event/cancel pending의 최종 durable 상태와 broker 대조를 보장하지 않은 채 `engine.stop()` 후 `os._exit(0)` 한다.
- 현재 테스트는 `tests/test_risk_sell_state_machine.py`에 거부와 cancel-request 대기/확인 후 재주문 두 사례만 있고, `tests/test_risk_restart_reconcile.py`, `tests/test_risk_late_session.py`는 없다. Review상 partial fill, duplicate fill, retry limit, cancel failure/confirmation timeout, restart, late-session failure path가 실행되지 않았다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `engine.py`

다음 기존 심볼을 보완한다.

- `TradingEngine._load_runtime_config`: 기존 risk timeout 설정을 유지하고 유한 양수/0 이상으로 정규화한다. `RISK_CANCEL_CONFIRM_TIMEOUT_SEC`와 `RISK_RECONCILE_INTERVAL_SEC`가 실제 dispatcher에서 사용되도록 한다.
- `TradingEngine.manage_pending_orders`: risk event/order와 일반 order를 분리 호출한다. risk order는 `_check_stale_risk_order`, risk reconcile/timeout handler, `_process_risk_retry`만 거치며 `_retry_sell_after_cancel`, `pending_resell`, `cancel_in_progress`를 거치지 않는다.
- `_get_open_risk_order` 또는 `OrderManager` helper 사용부: event id와 local/broker id를 기준으로 단 하나의 열린 risk sell을 식별한다.
- `_check_stale_risk_order`: 주문 timeout 후 broker `cancel_order` 성공은 취소 요청 접수일 뿐이다. `CANCEL_REQUESTED`와 request timestamp를 durable하게 기록하고, pending 대조 전에는 registry 삭제·재주문하지 않는다. `RISK_CANCEL_CONFIRM_TIMEOUT_SEC` 초과 시 broker 대조가 없거나 실패하면 `MANUAL_INTERVENTION_REQUIRED`로 terminal 처리한다.
- risk reconcile helper(신규 또는 동등한 private method): `RISK_RECONCILE_INTERVAL_SEC` 간격으로 broker pending 결과를 대조한다. 동일 broker id가 pending/partial이면 기존 주문과 mapping/context를 유지하고 재주문하지 않는다. pending에서 사라졌고 보유 잔량이 남는 것이 확정된 경우에만 `RETRY_PENDING`으로 전이한다. 조회 실패·빈 목록을 성공으로 오인·symbol/side/id가 모호한 경우는 manual intervention이다.
- `_process_risk_retry`/`_submit_risk_sell`: retry delay와 durable attempt count를 적용하고 최대 횟수 초과, reject, exception, storage update 실패는 `MANUAL_INTERVENTION_REQUIRED`로 끝낸다. 새 주문은 risk metadata와 같은 parent event/idempotency key를 유지하며 현재 보유 잔량과 broker 잔량 중 보수적으로 작은 수량만 제출한다.
- `sync_pending_orders`/`_restore_risk_events`: 재시작 시 계좌 보유수량과 broker pending 목록을 먼저 확보한 뒤 다음 matrix를 구현한다.
  1. 보유 잔량 0이면 추가 주문 없이 `CLOSED`.
  2. event의 broker id와 동일한 pending SELL이면 local order/mapping/context 복구, partial 상태 유지, 주문 0건.
  3. `CANCEL_REQUESTED`는 pending 부재가 확인되고 confirmation timeout이 지나지 않은 동안 재주문 금지.
  4. broker terminal이 확정되고 잔량이 남으며 retry budget이 있으면 `RETRY_PENDING`.
  5. broker 조회 실패, event에 broker/local id가 없거나 다수 후보로 모호한 경우 `MANUAL_INTERVENTION_REQUIRED`, 자동 재전송 금지.
- `on_fill`: risk event id로 주문을 찾고 partial/full 전이를 durable하게 기록한다. 중복/누적 chejan은 기존 정규화 규칙을 사용해 포지션·손익·event를 중복 반영하지 않는다.
- heartbeat/종료에서 호출할 risk 상태 관찰 helper(신규): stale 가격으로 `STOP_DETECTED`를 만들지 않고 열린 event, cancel pending, manual intervention, 잔량을 로그/Telegram에 기록한다. `on_real_tick`의 RiskGuard 우선순위는 그대로 둔다.

### 3.2 `core/models.py`

`Order` dataclass에 기본값을 가진 정식 필드를 추가한다(기존 positional construction 호환).

- `purpose` 기본값은 일반 주문을 의미하는 빈 값, risk 주문은 정확히 `RISK_STOP`.
- `risk_event_id`, `broker_order_id`를 명시적으로 보존한다.
- local `order_id`와 broker order number를 혼동하지 않는다.

### 3.3 `core/order_manager.py`

- `get_open_risk_sell_order_by_symbol(symbol)` 또는 event id 기준 동등 helper를 추가한다.
- broker↔local mapping을 보존하면서 risk order만 조회할 수 있게 한다.
- 부분체결 잔량은 local `qty-filled_qty`와 broker `unfilled_qty` 중 안전한 작은 값을 사용하도록 helper 또는 호출 계약을 명확히 한다.
- 일반 open-order/sell 조회와 신규매수 중복방지 동작은 회귀시키지 않는다.

### 3.4 `infra/sqlite_store.py`

기존 additive migration을 유지한다. 이미 있는 `attempt_count`, `cancel_requested_at`, `last_action_at`의 의미를 재사용하고 중복 컬럼을 만들지 않는다.

- risk event state, local/broker id, attempt count, cancel timestamp, last action, last error, qty를 원자적으로 갱신한다.
- manual intervention event는 기본 자동처리 조회에서 제외하고 `include_manual=True`로만 관찰 가능하게 한다.
- update/query 오류를 빈 성공 결과로 반환하지 않는다. 엔진이 자동 재주문하지 않고 manual intervention으로 fail-closed 할 수 있게 한다.

### 3.5 `main_live.py`

- `_recover_broker_session`: 기존 `14:40` 이후 reconnect 보류 정책은 유지한다. 보류를 risk 성공으로 기록하지 않고 열린 risk 상태 관찰/알림은 계속한다.
- `on_heartbeat`: market phase/stale tick 유무와 독립적으로 risk reconciliation/status observation을 수행한다. 장외/15:20 이후에도 이미 제출된 risk order의 pending/timeout/manual 상태를 확인하되, 새 가격 기반 stop은 생성하지 않는다. 기존 stale reconnect 정책 자체를 완화하지 않는다.
- `shutdown`: `os._exit(0)` 전에 열린 risk event, `CANCEL_REQUESTED`, manual intervention을 로그/Telegram에 남기고 가능한 마지막 `sync_account` 및 `sync_pending_orders`를 bounded하게 시도한다. 실패는 성공으로 포장하지 않는다. 일반 shutdown/조건검색 정책은 유지한다.

### 3.6 테스트

기존 `tests/test_risk_guard.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_event_recovery.py`, `tests/test_risk_sell_state_machine.py`는 유지·확장한다.

- `tests/test_risk_restart_reconcile.py` 신규: 기존 SQLite event + 새 engine + fake broker의 pending/position 조합을 검증한다. 동일 pending 보존, partial 잔량, zero-position close, missing/ambiguous/조회 예외 manual, `CANCEL_REQUESTED` 재주문 금지를 포함한다.
- `tests/test_risk_late_session.py` 신규: clock monkeypatch로 14:40 이후 reconnect blocked, 15:20 이후 stale recovery blocked, 15:35 shutdown 경계를 검증한다. 열린 risk 상태 로그/관찰은 유지되고 stale 가격만으로 주문하지 않음을 확인한다.
- `test_risk_sell_state_machine.py` 확장: partial fill, duplicate fill, cancel failure, cancel confirmation timeout, pending 지속, pending 소멸 후 risk-only retry, retry limit, reject/exception을 포함한다.
- 실제 `sleep`, 키움 COM, live broker는 사용하지 않는다. fake broker는 place/cancel 호출 기록, 반환값/예외, pending 목록, partial fill, reconnect 상태를 주입할 수 있어야 한다.

## 4. 불변조건 및 안전 제약

1. 동일 risk event에는 열린 risk sell이 최대 하나이고, `CANCEL_REQUESTED` 확인 전 재주문은 0건이다.
2. broker API 성공은 체결 성공이 아니다. fill callback 또는 계좌/pending 대조 전에는 미체결로 유지한다.
3. cancel return 0은 요청 접수일 뿐이다. confirmation timeout은 bounded하게 manual intervention으로 전환한다.
4. risk 경로는 일반 시간 게이트, `pending_resell`, 일반 retry/cancel flag, grace, trend-hold, news, daily cache에 의존하지 않는다.
5. stale/reconnect 부재는 새 가격 기반 stop을 만들지 않는다. 유효 실시간 tick에서만 RiskGuard가 stop을 감지한다.
6. `SELL_FILLED`, `CLOSED`, `MANUAL_INTERVENTION_REQUIRED`는 자동 재주문하지 않는 terminal 상태다.
7. retry delay/max count는 SQLite에 보존하며 무한 cancel/retry loop를 허용하지 않는다.
8. Python 3.8에서 compile/test 가능해야 하며 기존 RiskGuard 기본 동작과 일반 매도 회귀가 없어야 한다.
9. 로그/DB/알림에는 가능한 경우 `risk_event_id`, idempotency key, symbol, qty, state, reason, attempt count가 포함되고 비밀값은 포함하지 않는다.

## 5. Acceptance tests

### 손절 전용 상태 머신

1. timeout 시 risk cancel 호출은 1회이고 event는 `CANCEL_REQUESTED`; broker pending이 계속되면 주문 추가 0건이다.
2. cancel return 0 후 `RISK_CANCEL_CONFIRM_TIMEOUT_SEC`가 지나고 대조가 없으면 `MANUAL_INTERVENTION_REQUIRED`, 추가 cancel/retry 0건이다.
3. cancel 실패/예외도 manual intervention이고 일반 매도 retry로 우회하지 않는다.
4. partial 40/100 후 event가 `SELL_PARTIAL`이고 cancel/retry 수량은 60이다. 중복 fill은 qty/PnL을 중복 반영하지 않는다.
5. pending 소멸과 잔량이 broker 대조로 확인된 뒤에만 `RETRY_PENDING` 및 risk-only 재주문이 발생하며 일반 시간 게이트 호출은 0회다.
6. retry max 초과, risk reject, risk exception, SQLite update/query 실패는 manual intervention이고 이후 tick/heartbeat에도 주문 수가 증가하지 않는다.
7. 일반 매도는 기존 `_auto_sell_allowed_now`, `pending_resell`, 일반 timeout 정책을 그대로 사용한다.

### broker 대조 및 재시작

8. 새 engine이 기존 event와 동일 broker pending SELL을 찾으면 local/broker mapping/context를 복구하고 새 주문 0건이다.
9. 동일 pending partial은 남은 수량을 보존하며 duplicate restore가 없다.
10. 재시작 후 보유수량 0이면 event를 `CLOSED`로 만들고 broker 주문 0건이다.
11. pending 조회 예외, broker/local id 없음, symbol/side/id 모호성은 manual intervention이며 빈 목록 성공이나 자동 재전송이 없다.
12. 재시작 `CANCEL_REQUESTED` event는 confirmation 대조 전 재주문하지 않는다.

### stale/reconnect/장마감

13. 14:40 이후 reconnect가 보류되어도 열린 risk event 상태 관찰/알림은 유지되고 reconnect 성공으로 기록되지 않는다.
14. 15:20 이후 stale recovery가 중지되어도 heartbeat가 열린 risk/cancel/manual 상태를 관찰하며, stale 가격만으로 새 stop 주문을 만들지 않는다.
15. 15:35 shutdown 직전 마지막 bounded account/pending reconciliation과 열린 risk 상태 로그가 수행되고, 조용한 event 삭제가 없다.
16. 유효 tick이 실제로 도착하면 장중 일반 매도 시간 게이트와 무관하게 RiskGuard가 먼저 stop을 제출한다. 유효 tick이 전혀 없으면 stop 주문은 0건이다.
17. 기존 전체 테스트, Python 3.8 compile check, `git diff --check`가 통과한다.

## 6. 검증 명령

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/models.py','core/risk_guard.py','core/order_manager.py','engine.py','infra/sqlite_store.py','main_live.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

live 실행, 키움 연결, 실제 주문 명령은 검증으로 간주하지 않으며 실행하지 않는다.

## 7. 롤백 고려사항

- SQLite 파일은 배포 전 백업한다. schema는 additive이며 기존 event/order/fill/trade 데이터를 삭제하지 않는다.
- 롤백 단위는 `engine.py` risk reconcile/timeout 변경, `core/models.py` metadata, `core/order_manager.py` helper, `infra/sqlite_store.py` 상태 갱신, `main_live.py` heartbeat/shutdown 관찰, 신규 테스트로 분리한다.
- 이미 broker에 제출된 risk 주문을 코드 롤백 중 취소하거나 재전송하지 않는다. 먼저 계좌 보유수량과 미체결 주문을 대조하고 event 감사 기록을 보존한 뒤 수동 처리한다.
- 구현이 불완전하거나 broker/DB 대조가 실패하면 일반 매도 경로로 우회하지 말고 `MANUAL_INTERVENTION_REQUIRED`로 fail-closed 한다.
- 구버전 프로세스와 새 상태 schema를 동시에 실행하지 않는다. 전환 중 신규 자동매매를 중지하고 단일 프로세스만 DB를 소유한다.
