# TASK-001 테스트 보고서

## 실행 환경

- Python: `Python 3.8.10` (`C:\Users\bread\AppData\Local\Programs\Python\Python38-32\python.exe`)
- pytest: 설치되지 않음 (`No module named pytest`)
- 실제 브로커/live 실행: 실행하지 않음

## 실행 결과

### 1. 지정 pytest 테스트 — 실행 불가

명령:

```powershell
python -m pytest tests/test_risk_guard.py tests/test_engine_risk_priority.py tests/test_risk_event_recovery.py
```

결과: **BLOCKED**

```text
C:\Users\bread\AppData\Local\Programs\Python\Python38-32\python.exe: No module named pytest
```

### 2. 대상 파일 문법 검사 — 통과

명령:

```powershell
python -B -c "from pathlib import Path; files=['main_live.py','engine.py','config_live.py','build_daily_strategy_snapshot.py','core/risk_guard.py','infra/sqlite_store.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
```

결과: **PASS** — `syntax ok`

### 3. pytest 없는 환경에서 순수 RiskGuard/SQLite 테스트 직접 실행 — 통과

명령:

```powershell
python -c "import tempfile; from pathlib import Path; from tests.test_risk_guard import test_boundary_triggers_and_invalid_values_do_not, test_open_order_and_persisted_event_are_idempotent; from tests.test_risk_event_recovery import test_risk_event_is_durable_and_recovered; test_boundary_triggers_and_invalid_values_do_not(); test_open_order_and_persisted_event_are_idempotent(); with_dir=tempfile.TemporaryDirectory(); test_risk_event_is_durable_and_recovered(Path(with_dir.name)); with_dir.cleanup(); print('direct risk tests ok')"
```

결과: **PASS** — `direct risk tests ok`

### 4. 엔진 우선순위 테스트 직접 실행 — 실패

명령:

```powershell
python -c "from tests.test_engine_risk_priority import test_risk_guard_runs_before_external_data_and_strategy; test_risk_guard_runs_before_external_data_and_strategy(); print('priority test ok')"
```

결과: **FAIL — 첫 actionable failure**

```text
TypeError: 'type' object is not subscriptable
...
core\\risk_manager.py, line 18, in RiskManager
def can_trade(self, signal: Signal, portfolio: Portfolio) -> tuple[bool, str]:
```

현재 Python 3.8에서 `tuple[...]` 타입 힌트 import가 실패하여 `engine.TradingEngine`을 로드하지 못했다. Python 3.10+ 또는 프로젝트 호환 `.venv`에서 재실행해야 한다.

## 전체 테스트 스위트

첫 엔진 테스트 import 실패 후 지침에 따라 중단했다. pytest가 설치되지 않았고, 현재 Python 3.8 호환성 오류로 엔진/복구 acceptance 테스트 전체를 완료하지 못했다.

## 커버리지 및 남은 검증

- 검증됨: RiskGuard 경계값, invalid 입력, idempotency; SQLite risk event 생성/중복/갱신/종료; 대상 파일 syntax.
- 미검증: `on_real_tick` RiskGuard 우선순위, 실제 engine risk 주문 제출, 재시작 복구의 engine 연계, fill/partial/timeout/retry/manual intervention 경로.
- 실제 브로커 주문, `RUN_MODE=live`, 키움 연결은 실행하지 않았다.
