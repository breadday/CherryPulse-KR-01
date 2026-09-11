# TASK-003 테스트 보고서

## 실행 환경

- Python: `Python 3.8.10`
- `.venv\Scripts\python.exe`는 작업 트리에 없어 시스템 `python`으로 실행했다.
- 실제 키움 COM, `RUN_MODE=live`, 계좌/주문 경로는 실행하지 않았다.

## 검증 결과

### 1. 협소 관련 테스트

명령:

```powershell
python -m pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_guard.py tests/test_engine_risk_priority.py tests/test_risk_event_recovery.py
```

결과: **PASS** — `6 passed in 1.01s`

### 2. 전체 pytest

명령:

```powershell
python -m pytest -q
```

결과: **PASS** — `6 passed in 0.95s`

### 3. Python 문법 검사

명령:

```powershell
python -B -c "from pathlib import Path; files=['core/models.py','core/risk_guard.py','core/order_manager.py','engine.py','broker/kiwoom_broker.py','broker/kiwoom_stub.py','main_live.py','config_live.py','infra/sqlite_store.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
```

결과: **PASS** — `syntax ok`

### 4. Diff whitespace 검사

명령:

```powershell
git diff --check
```

결과: **PASS** — whitespace 오류 없음. Git이 `engine.py`, `infra/sqlite_store.py`의 LF/CRLF 변환 가능성을 경고했으나 검사 자체는 통과했다.

## 누락/제한된 커버리지

- 명세가 요구한 `tests/test_risk_restart_reconcile.py`와 `tests/test_risk_late_session.py` 파일은 현재 작업 트리에 존재하지 않아 실행하지 못했다.
- 따라서 재시작 broker 대조, late-session stale/reconnect/shutdown 경계의 전용 acceptance coverage는 확인되지 않았다.
- 현재 전체 pytest가 수집한 테스트는 6개이며, 실제 broker 취소 확정·계좌 대조 및 live 실행 증거는 없다.
