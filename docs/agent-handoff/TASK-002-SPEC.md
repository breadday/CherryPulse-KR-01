# TASK-002 구현 명세 — Python 3.8 RiskGuard 테스트 호환성

상태: IMPLEMENTATION_CONTRACT
기준: 로컬 소스 현재 상태(2026-09-10)

## 1. 목표와 범위

Python 3.8에서 TASK-001의 RiskGuard 관련 pytest가 import 단계에서 실패하지 않도록, RiskGuard 테스트가 직접 또는 간접적으로 import하는 타입 표기만 Python 3.8 호환 형태로 바꾼다. 손절 계산, 주문 우선순위, idempotency, SQLite 상태 전이 및 기타 매매 로직은 변경하지 않는다.

범위는 다음 두 production 파일의 타입 표기에 한정한다.

- `core/risk_manager.py`
- `engine.py`

테스트 코드, 브로커 transport, 설정값, 전략 조건, 주문 상태 로직은 변경하지 않는다. 이 작업은 코드 수정 작업이므로 live 실행이나 키움 연결을 수행하지 않는다.

## 2. 현재 동작과 근거

- `tests/test_risk_guard.py`는 `core.risk_guard`를 직접 import하고 순수 손절 판정 및 중복 제출 방지를 검사한다.
- `tests/test_engine_risk_priority.py:1-4`는 `engine.TradingEngine`을 import한다.
- `engine.py:13`은 `core.risk_manager.RiskManager`를 import하고, `core/risk_manager.py:18`의 `RiskManager.can_trade`가 `tuple[bool, str]`를 사용한다. Python 3.8에서는 builtin `tuple`이 해당 방식으로 subscript되지 않아 `engine` import가 실패할 수 있다.
- 위 표기를 고친 뒤에도 Python 3.8에서 `engine.py`를 import하면 다음 PEP 585 표기가 평가될 수 있다: `engine.py:326`의 `list[str]`, `647`와 `693`의 `list[dict]`, `2331`의 `tuple[bool, float, float]`.
- `core/risk_guard.py` 자체의 `RiskPosition`/`RiskDecision`은 현재 `object`, `str`, `int`, `float`만 사용하며, 이번 호환성 문제의 직접 원인인 builtin generic 표기가 없다.
- 현재 테스트 파일은 `tests/test_risk_guard.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_event_recovery.py` 3개다.
- TASK-001 구현 보고서에는 기본 Python 3.8에서 기존 `risk_manager.py`의 `tuple[...]` 타입 힌트 때문에 priority 테스트 직접 실행이 불가능했다고 기록되어 있다(`docs/agent-handoff/TASK-001-IMPLEMENTATION.md:17-18`).
- 저장소의 현재 미커밋 변경(`engine.py`, `infra/sqlite_store.py`, `core/risk_guard.py`, `tests/`)은 TASK-001 작업물일 수 있으므로 되돌리거나 정리하지 않는다.

## 3. 변경 파일과 정확한 심볼

### 3.1 `core/risk_manager.py`

- `typing.Tuple`을 import한다.
- `RiskManager.can_trade`의 반환 표기 `tuple[bool, str]`를 `Tuple[bool, str]`로 바꾼다.
- 함수 본문, 조건 순서, 반환 문자열, `RiskManager`의 설정값은 한 글자도 의미 변경하지 않는다.

### 3.2 `engine.py`

- `typing.List`, `typing.Dict`, `typing.Tuple`을 import한다(기존 typing import가 있으면 중복 import하지 않고 확장한다).
- 다음 반환 표기를 Python 3.8 호환 표기로 치환한다.
  - `_format_strategy_diagnostics_lines`: `list[str]` → `List[str]`
  - `_load_daily_candles_from_csv`: `list[dict]` → `List[Dict]`
  - `_get_daily_candles_cached`: `list[dict]` → `List[Dict]`
  - `_is_long_bull_candle`: `tuple[bool, float, float]` → `Tuple[bool, float, float]`
- 이외의 `engine.py` 실행문, 메서드 본문, RiskGuard 호출 순서, 주문/체결/복구 상태 전이는 수정하지 않는다.

`from __future__ import annotations`를 대체 수단으로 선택할 경우에도 위 심볼의 표기가 Python 3.8에서 import되는 모든 경로에서 평가되지 않아야 하며, 두 방식을 불필요하게 함께 적용하지 않는다. 변경은 최소화하고 명시적 `typing` 표기 치환을 우선한다.

## 4. 불변조건과 안전 제약

1. Python 3.8에서 `from core.risk_guard import ...`, `from engine import TradingEngine`이 모두 성공해야 한다.
2. `RiskGuard.check_stop`의 경계 판정 `pnl <= stop_loss_pct`를 변경하지 않는다.
3. invalid 입력(`None`, 0, 음수, 비수치, NaN, infinity)에서는 계속 주문하지 않고 `INVALID_INPUT` 결과를 유지한다.
4. 유효 손절 틱은 외부 점수/일봉/전략보다 먼저 처리되고, 중복 주문 억제 및 손절 전용 제출 경로가 그대로 유지되어야 한다.
5. SQLite `risk_events` 생성/갱신/복구, 부분체결·완전체결 상태, 실패 시 수동개입 상태를 변경하지 않는다.
6. `broker/kiwoom_broker.py`를 수정하지 않으며 `RUN_MODE=live` 또는 실제 계좌 주문을 실행하지 않는다.
7. `.env`, 계좌번호, 비밀번호, 토큰을 읽거나 출력하지 않는다.
8. Python 3.8 호환성 수정 외에 전략 손절값, 일반 자동매도 시간 게이트, timeout/retry 정책을 조정하지 않는다.

## 5. acceptance tests

### import 및 정상 경로

- Python 3.8 인터프리터에서 `from core.risk_guard import RiskGuard, RiskPosition`가 성공한다.
- Python 3.8 인터프리터에서 `from engine import TradingEngine`가 성공한다.
- `RiskPosition("A", 98, 100, 10, -0.02)`는 `STOP_DETECTED`를 반환하고, 정확한 경계값에서 trigger된다.
- `tests/test_engine_risk_priority.py`에서 손절 틱은 broker 주문 1건/100주를 만들고 strategy 호출은 0회이며, 외부 데이터 호출보다 먼저 처리된다.
- `tests/test_risk_event_recovery.py`에서 SQLite 이벤트 생성, 동일 idempotency key 중복 억제, partial update, filled 후 open 목록 제거가 기존과 동일하게 통과한다.

### 실패 및 경계 경로

- `price`, `avg_price`, `qty`, `stop_loss_pct` 각각에 `None`, 0, 음수, `"x"`, NaN, infinity를 주입했을 때 `INVALID_INPUT`이며 broker 호출은 0건이다.
- 동일 틱을 반복하거나 열린 매도 주문/`SELL_PARTIAL` 상태가 있는 경우 broker 호출이 추가되지 않는다.
- Python 3.8에서 import 시 `TypeError: 'type' object is not subscriptable` 또는 이에 준하는 builtin generic 타입 오류가 발생하지 않는다.
- 기존 전체 테스트의 failure path(주문 거부/예외, SQLite 중복 이벤트 및 복구 fixture)가 호환성 변경 전과 동일한 결과를 낸다.

### 검증 명령

구현자는 실제 Python 3.8 환경(프로젝트 `.venv`가 Python 3.8이면 그것을 우선)에서 다음을 순서대로 실행하고 전체 출력을 보고서에 기록한다.

```powershell
.venv\Scripts\python.exe --version
.venv\Scripts\python.exe -B -c "from core.risk_guard import RiskGuard, RiskPosition; from engine import TradingEngine; print('py38 imports ok')"
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['core/risk_guard.py','core/risk_manager.py','engine.py','infra/sqlite_store.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short
```

`pytest -q`는 특정 RiskGuard 테스트만이 아니라 저장소의 전체 테스트를 재실행해야 한다. Python 3.8 실행 파일 또는 pytest가 없으면 성공으로 포장하지 말고 명령과 오류를 보고서에 남긴다. live 실행/키움 API 테스트는 acceptance 대상이 아니다.

## 6. 롤백 고려사항

- 변경 파일은 `core/risk_manager.py`와 `engine.py`의 typing import 및 네 개 타입 표기만 되돌리면 된다. TASK-001의 RiskGuard 구현, SQLite schema, 테스트 파일은 롤백하지 않는다.
- 롤백 전후 `git diff`로 매매 로직 변경이 섞이지 않았는지 확인한다.
- 호환성 수정 롤백 시 Python 3.8 import 실패가 재발할 수 있으므로, 실제 Python 3.8 전체 테스트 결과를 확인한 뒤에만 롤백한다.
- 이미 존재하는 `risk_events` 데이터, 주문, 체결, 보유 포지션은 이 작업에서 건드리지 않는다. 실패 시에도 broker 주문을 취소하거나 재전송하지 말고 계좌/미체결 상태를 별도로 대조한다.
