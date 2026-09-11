# TASK-006 테스트 보고서

## 실행 결과

- 대상: `TASK-006-SPEC.md`, `TASK-006-IMPLEMENTATION.md`
- 좁은 관련 테스트:
  - 명령: `python -m pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_event_recovery.py tests/test_engine_risk_priority.py tests/test_risk_guard.py`
  - 결과: **통과 — 8 passed in 0.91s**
- 전체 테스트:
  - 명령: `python -m pytest -q`
  - 결과: **통과 — 8 passed in 1.05s**
- Python 문법 검사:
  - 명령: `python -B -c "from pathlib import Path; files=['core/models.py','core/order_manager.py','engine.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"`
  - 결과: **통과 — `syntax ok`**
- diff 검사:
  - 명령: `git diff --check`
  - 결과: **통과** (개행 변환 경고만 출력)

## 호출 횟수 및 coverage

현재 자동화된 8개 테스트는 risk sell state machine, risk event recovery, risk priority, RiskGuard를 커버한다. 테스트 실행 중 실패는 없었다.

구현 보고서에 기재된 제한과 같이 `core.models.Order` 정식 risk 필드, 명시적 local↔broker 양방향 binding, broker ID 기반 fill/restart 매핑은 구현되지 않았다. `tests/test_risk_restart_reconcile.py`도 존재하지 않아 재시작 복구, pending 반복 sync 중복 방지, partial 40/100→60 복구, pending/account 예외 및 ambiguous identity failure-path는 자동 검증되지 않았다.

따라서 전체 pytest는 통과했지만 TASK-006 명세의 전체 acceptance coverage를 충족한다고 판단할 수 없다. 실 broker/COM, live 실행 및 실제 주문·취소 호출은 수행하지 않았다.
