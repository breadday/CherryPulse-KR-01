# TASK-001 구현 명세 — RiskGuard 독립화

상태: IMPLEMENTATION_CONTRACT
기준: 로컬 소스 현재 상태(2026-09-10)

## 1. 목표와 범위

CherryPulse의 보유 포지션 위험 감시를 전략/종목선정과 분리한다. 외부 후보 입력은 신규 진입 유니버스에만 사용하고, 보유 포지션의 손절 감지와 손절 주문 상태 관리는 후보 파일, 전략 신호, 뉴스, 일봉 캐시, grace, trend-hold, 일반 자동매도 시간 게이트와 독립시킨다. 브로커 주문 전송 구현은 수정하지 않는다.

이번 구현 범위는 다음 두 단계다.

1. 틱 처리에서 `RiskGuard`를 최우선으로 호출하고 손절 전용 주문 경로를 만든다.
2. 손절 이벤트와 주문 진행 상태를 SQLite에 기록하고 재시작 시 복구한다.

## 2. 현재 동작과 근거

- `engine.py:27`에서 `RiskManager`를 생성하지만, 실제 청산 검사는 `TradingEngine._check_auto_exit`이며 `RiskManager.can_trade`와 연결되지 않는다.
- `engine.py:1968-2052`의 `TradingEngine.on_real_tick`은 먼저 외부 점수(`_build_external_scores`), 틱 등록, 일봉 캐시(`_get_daily_candles_cached`)를 수행한 뒤 `TradingEngine._check_auto_exit`를 호출한다. 따라서 위험 경로가 조회/캐시 예외의 영향을 받을 수 있다.
- `engine.py:2333-2517`의 `_check_auto_exit`는 전략명과 전략별 `stop_loss_pct`를 조회하고, grace를 계산하며, trend-hold를 갱신한 후 손절을 판단한다.
- `engine.py:2519-2600`의 `_submit_auto_sell`은 모든 자동매도에 `_auto_sell_allowed_now`를 적용한다. 현재 `AUTO_SELL_START_HHMM=09:03`, `AUTO_SELL_END_HHMM=15:20`이므로 15:20 이후 손절도 차단된다.
- `_check_auto_exit`의 손절은 `not stop_loss_grace_active` 조건으로 지연되며, breakeven 청산은 trend-hold에 의해 건너뛸 수 있다.
- `engine.py:2983-3005`의 `on_tick`은 손절과 무관한 `strategy.generate_signal`을 먼저 호출한다. 전략 신호가 없으면 즉시 반환한다.
- `main_live.py:613-627`은 `_should_route_tick`을 통과한 틱만 엔진에 전달한다. 다만 `_all_watch_codes`(`main_live.py:384-388`)에는 보유종목과 미체결 종목이 포함되어 있으므로 이 보존 동작은 유지해야 한다.
- `main_live.py:631-766`, `1031-1072`에는 stale 실시간 데이터 및 reconnect 차단/재시도 정책이 있다. 이 정책은 연결 복구 정책이지 손절 판정의 조건이어서는 안 된다. 틱이 실제로 끊긴 경우 임의의 stale 가격으로 자동주문하지 말고 상태를 수동개입 대상으로 남긴다.
- `engine.py:1690-1829`는 계좌 및 미체결 주문을 복구하지만 손절 감지/상태 이벤트는 복구하지 않는다. `pending_resell`, `sell_in_progress`, `resell_retry_count` 등은 메모리 상태다.
- `infra/sqlite_store.py:28-190`에는 `signals`, `orders`, `fills`, `trades` 등은 있으나 `risk_events` 저장 구조가 없다.
- 전략별 현재 손절 기준은 `config_live.py` 및 `STRATEGY_RUNTIME_CONFIG` 값의 단일 출처로 유지한다. `docs/SOURCE_ANALYSIS.md:60-64`에 현재 운영 기준이 문서화되어 있다. 구현에서 기준값을 튜닝하지 않는다.

## 3. 변경 파일과 정확한 심볼

### 3.1 신규: `core/risk_guard.py`

다음 순수 판정/상태 인터페이스를 추가한다. 이 모듈은 전략, 뉴스 provider, 일봉 loader, broker, `Portfolio` 전체 객체를 import하거나 호출하지 않는다.

- `RiskPosition` 또는 동등한 불변 입력 모델: `symbol`, `price`, `avg_price`, `qty`, `stop_loss_pct`만 필수 입력. 선택적으로 `position_key`/`entry_id`를 둔다.
- `RiskDecision` 또는 동등한 결과 모델: `triggered`, `reason`, `symbol`, `qty`, `pnl_pct`, `event_type`.
- `RiskGuard.check_stop(position)`: 가격/평단/수량이 정상이고 `qty > 0`, `price > 0`, `avg_price > 0`일 때만 `(price-avg_price)/avg_price <= stop_loss_pct`를 판정한다. 누락/NaN/무한/비수치/비양수 값은 주문하지 않고 명시적 `INVALID_INPUT` 결과를 반환한다.
- `RiskGuard.should_submit(symbol, position_key, open_sell_exists, state)`: 동일 포지션에 이미 `STOP_DETECTED` 이후 진행 중인 주문이 있으면 재주문하지 않는다. 수량 0이면 no-op이다.
- `RiskGuard`의 상태는 프로세스 메모리에만 의존하지 않도록 저장소 adapter를 통해 읽고 쓴다. 저장소 장애 시 안전하게 새 주문을 반복하지 않으며 `MANUAL_INTERVENTION_REQUIRED`를 남길 수 있어야 한다.

손절 판정은 전략별 현재 `stop_loss_pct`를 호출자가 제공하되, guard 내부에서 grace/tick 수/시간/뉴스/추세를 검사하지 않는다. 기존 전략별 손절 기준 자체는 변경하지 않는다.

### 3.2 `engine.py`

- import 및 `TradingEngine.__init__`: `RiskGuard`를 생성하고, 기존 `RiskManager`는 신규 매수 방어용으로만 남긴다. `RiskManager`를 제거하거나 손절 판단에 재사용하지 않는다.
- 신규 `TradingEngine._check_risk_guard(tick)`: 현재 포트폴리오의 해당 보유 포지션만 읽어 guard 입력을 만들고, 손절 decision을 기록한 뒤 손절 전용 제출 함수로 연결한다. 포지션이 없거나 비정상 입력이면 주문하지 않는다.
- 신규 `TradingEngine._submit_risk_sell(symbol, qty, reason, risk_event_id/idempotency_key)`: `_auto_sell_allowed_now`를 호출하지 않고, 일반 자동매도/익절 함수와 분리한다. 기존 `broker.place_order(signal)`, `OrderManager.register`, `_record_order_snapshot`, paper fill 처리, route context 연결은 재사용하되 브로커 파일은 수정하지 않는다. 손절 주문은 시장가 매도이며 `qty`는 현재 보유수량과 요청량 중 작은 값이다.
- `TradingEngine.on_real_tick`: 유효한 가격과 기본 `TickData`를 만든 뒤 **일봉 캐시, 뉴스/외부 점수, 전략 실행보다 먼저** `_check_risk_guard`를 호출한다. guard가 주문을 제출하면 해당 틱의 신규진입 처리를 중단한다. 손절 경로의 예외가 전략 경로를 깨지 않도록 분리된 try/except와 로그를 둔다.
- `TradingEngine._check_auto_exit`: 기존 손절 분기와 `_submit_auto_sell` 호출은 제거하거나 guard 경로로 위임해 중복 손절이 발생하지 않게 한다. 익절/부분매도/trailing/일반 청산은 기존 순서와 정책을 보존한다. 특히 guard 호출에는 `_in_stop_loss_grace_window`, `_update_trend_hold_state`, `_auto_sell_allowed_now`를 넣지 않는다.
- `TradingEngine.on_fill` 및 주문 상태 처리: risk 주문의 event id/idempotency key를 추적하고 `SELL_PARTIAL`, `SELL_FILLED`를 기록한다. 거절/예외/취소 실패/최대 재시도 초과는 `MANUAL_INTERVENTION_REQUIRED`로 전환하고 Telegram과 로그에 남긴다. 기존 일반 매도 정책과 상태를 섞지 않는다.
- `TradingEngine.start` 또는 계좌 동기화 직후: 저장된 미종결 risk event와 현재 계좌/미체결 매도 주문을 대조해 `risk_guard.restore_pending()` 같은 복구 루틴을 호출한다. 이미 수량 0이면 이벤트를 종료 처리하고, 잔여 수량과 열린 매도 주문이 있으면 동일 주문을 재전송하지 않는다.
- `_check_stale_sell_order`/`_retry_sell_after_cancel`: 일반 자동매도 재시도와 risk 주문 재시도를 구분한다. risk 재시도에도 `SELL_ORDER_TIMEOUT_SEC`, `RETRY_SELL_MAX_COUNT` 같은 유한 timeout/최대횟수를 적용하고, 초과 시 수동개입 상태로 끝낸다. 무한 대기/무한 재주문은 금지한다.
- 신규/변경 로그에는 `risk_event_id`, `idempotency_key`, `symbol`, `qty`, `state`, `reason`을 포함한다. 손절 후 당일 재진입 차단(`BLOCK_STOPLOSS_SYMBOL_FOR_DAY`)은 유지한다.

### 3.3 `infra/sqlite_store.py`

- `_ensure_schema`에 `risk_events` 테이블을 추가한다. 최소 컬럼은 `id`(PK), `event_id`(UNIQUE), `idempotency_key`(UNIQUE), `created_at`, `updated_at`, `test_name`, `symbol`, `position_key`, `qty`, `price`, `avg_price`, `pnl_pct`, `reason`, `state`, `local_order_id`, `broker_order_id`, `attempt_count`, `last_error`, `raw_payload`다.
- 신규 메서드: `create_risk_event`, `update_risk_event`, `get_open_risk_events`, `get_risk_event_by_idempotency_key`. 기존 DB에 대해 `CREATE TABLE IF NOT EXISTS`로 비파괴 마이그레이션한다.
- unique 충돌은 중복 손절 이벤트로 간주해 기존 event를 반환한다. 저장 실패는 예외를 삼키고 성공으로 기록하지 말며, 엔진이 수동개입 상태로 전환할 수 있는 결과를 제공한다.
- 기존 `orders`/`fills`/`trades` 스키마와 기존 전략 성과 집계는 변경하지 않는다.

### 3.4 `main_live.py` (필요한 최소 변경)

- `_all_watch_codes`의 보유종목/미체결 주문 포함을 유지한다.
- `_should_route_tick` 또는 `on_filtered_real_tick` 수정 시 보유 포지션은 snapshot/universe에 없어도 계속 엔진으로 라우팅되어야 한다.
- stale/reconnect 차단 플래그를 RiskGuard 호출 조건으로 사용하지 않는다. 단, 실제 틱이 없는 동안 stale 가격으로 신규 손절 주문을 만들지는 않는다. reconnect 실패/장후반 복구 보류는 별도 알림과 수동개입 신호로 남긴다.
- 자동 종료를 손절 감시 우회 수단으로 변경하지 않는다. 브로커 연결/계좌 안전 검증과 실거래 차단은 유지한다.

### 3.5 테스트

현재 일반 `tests/` 스위트는 없다. 다음 파일을 새로 추가한다.

- `tests/test_risk_guard.py`: 순수 판정, invalid input, qty 0, 경계값, idempotency.
- `tests/test_engine_risk_priority.py`: fake broker/strategy/logger/store로 `on_real_tick` 호출 순서와 분리된 제출을 검증.
- `tests/test_risk_event_recovery.py`: SQLite fixture와 재시작을 흉내 내는 새 engine으로 상태 복구 및 중복 방지를 검증.

## 4. 불변조건과 안전 제약

1. `RUN_MODE=live`를 활성화하거나 실제 broker 주문을 테스트하지 않는다. 테스트 broker는 fake/stub이어야 한다.
2. `.env`, 계좌번호, 토큰, 비밀번호는 읽거나 출력하거나 수정하지 않는다.
3. `broker/kiwoom_broker.py`는 수정하지 않는다.
4. 손절 주문은 일반 자동매도 시간 제한, grace, trend-hold, 전략 신호, 뉴스, 일봉 캐시, stale/reconnect 차단에 의해 차단되지 않는다.
5. 실제 가격 틱이 없으면 guard는 자동주문을 추정하지 않는다. stale 데이터는 수동개입/관찰 상태를 만들 수 있으나 유효 가격으로 간주하지 않는다.
6. 손절은 `qty > 0`인 보유분에만 요청하며, 동일 `symbol + position_key + stop event`에 열린 매도 주문을 하나만 허용한다.
7. 중복 체결 이벤트는 기존 `on_fill`의 누적 체결 정규화와 함께 처리되어 포지션/손익을 중복 반영하지 않는다.
8. 저장소 기록 성공 전에는 `SELL_SUBMITTING`을 성공 상태로 확정하지 않는다. 저장소 장애, 주문 거절, 취소 실패, 재시도 한도 초과는 자동 성공으로 포장하지 않고 수동개입 상태로 남긴다.
9. 전략별 손절 퍼센트는 `config_live.py`의 기존 값을 사용하며 변경하지 않는다. 일반 익절/부분매도/trailing 정책도 회귀시키지 않는다.
10. 모든 API 대기와 재시도에는 기존 timeout 및 명시적 최대 횟수가 있어야 하며 무한 루프를 만들지 않는다.

## 5. acceptance tests

### 정상 경로

- 보유수량 100, 평단 10,000, 현재가 9,800, 손절 -1.5%에서 `STOP_DETECTED`와 손절 시장가 주문 100주가 발생한다.
- 현재가가 정확히 경계값일 때 손절하고, 경계 위에서는 주문하지 않는다.
- 장중 및 `AUTO_SELL_END_HHMM` 이후 모두 guard 주문이 제출된다. 일반 `_submit_auto_sell`은 시간 차단을 계속 적용한다.
- 전략이 `None`을 반환하거나 전략 함수가 예외를 내도 손절 주문은 제출된다.
- 일봉 캐시 실패와 뉴스 provider 예외를 주입해도 손절 주문은 제출된다.
- grace가 활성이고 trend-hold가 활성이어도 손절 주문은 제출된다.
- snapshot에 없는 보유종목도 `main_live`의 watch route를 통해 guard에 도달한다.

### 실패/경계 경로

- qty 0, price 0, avg_price 0, 음수값, `None`, 비수치, NaN, infinity 각각 주문 0건이며 `INVALID_INPUT` 로그/결과를 확인한다.
- 같은 틱을 두 번 보내고 저장소/OrderManager에 열린 매도 주문이 있으면 broker 호출은 1건뿐이다.
- 보유수량이 손절 감지 후 0이 되면 후속 틱에서 재주문하지 않는다.
- broker 주문 거절은 risk event를 `MANUAL_INTERVENTION_REQUIRED`로 남기고 Telegram/로그에 남긴다.
- timeout 후 취소 성공은 잔량에 대해서만 유한 횟수로 재주문하고, 취소 실패는 무한 재주문하지 않고 수동개입으로 끝낸다.
- 부분체결은 `SELL_PARTIAL`과 남은 수량을 저장하며, 남은 수량만 후속 처리한다. 완전 체결은 `SELL_FILLED`다.
- SQLite 쓰기 실패는 주문 성공/완료로 기록하지 않고 수동개입 결과를 반환하며 동일 주문을 무한 반복하지 않는다.
- 프로세스 재시작 fixture에서 `STOP_DETECTED`/`SELL_SUBMITTING`/`SELL_PARTIAL`과 local/broker order id를 복원한다. 계좌에 잔량과 열린 주문이 있으면 재전송하지 않는다.
- 재시작 후 계좌 잔량이 0이면 열린 risk event를 종료 처리하고 broker 호출은 0건이다.
- stale heartbeat/reconnect blocked 상태를 주입해도 guard의 이미 수신된 유효 틱 판정은 차단되지 않는다. 틱 자체가 없을 때는 자동주문하지 않고 수동개입/관찰 상태를 확인한다.

### 검증 명령

구현 후 다음을 실행하고 결과를 보고서에 기록한다.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_risk_guard.py tests/test_engine_risk_priority.py tests/test_risk_event_recovery.py
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['main_live.py','engine.py','config_live.py','build_daily_strategy_snapshot.py','core/risk_guard.py','infra/sqlite_store.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
```

기존 harness 명령은 추가로 실행할 수 있지만, live 실행 및 키움 연결 명령은 실행하지 않는다.

## 6. 외부 종목선정과 내부 로직의 책임 경계

외부 시스템은 `candidate.json` 또는 기존 `condition_snapshot.json`/SQLite 입력을 통해 후보와 전략 태그를 제공한다. `UniverseManager`, snapshot selector, 전략의 `generate_signal`은 신규 진입 후보/신호만 책임진다. RiskGuard는 후보에 없는 종목을 포함해 이미 보유한 모든 포지션의 현재가 기반 손절만 책임진다. 후보 입력 오류·부재·stale은 신규 진입을 막을 수 있지만 보유 포지션의 RiskGuard 호출과 위험 상태 복구를 막을 수 없다.

## 7. 롤백 고려사항

- 배포 전 기존 SQLite 파일을 백업하고 스키마 변경 전후를 확인한다. 새 `risk_events` 테이블은 기존 테이블을 삭제하거나 컬럼을 재작성하지 않는 additive migration이어야 한다.
- 구현 실패 시 `engine.py`의 RiskGuard 호출/신규 risk submit 경로를 이전 `_check_auto_exit`/`_submit_auto_sell` 경로로 되돌릴 수 있어야 한다. 기존 전략 손절값과 broker transport는 롤백 대상이 아니다.
- RiskGuard가 예외를 내거나 저장소 복구가 불가능하면 신규 진입보다 수동개입 알림을 우선하고, 자동 손절을 조용히 우회하지 않는다.
- 롤백 후에도 이미 broker에 제출된 주문을 취소하거나 재전송하지 말고, 계좌/미체결 조회로 실제 상태를 대조한다. `risk_events`의 감사 기록은 보존한다.
