# TASK-001 구현 보고서

## 변경 파일

- `core/risk_guard.py`: 전략/뉴스/일봉과 독립된 손절 판정, invalid 입력 방어, idempotency 판정 및 복구 adapter 추가.
- `engine.py`: 유효 틱에서 RiskGuard를 외부 점수·일봉 캐시·전략보다 먼저 호출하고, 일반 자동매도 시간 게이트를 거치지 않는 시장가 손절 제출 경로와 SQLite 상태 복구를 추가.
- `infra/sqlite_store.py`: 기존 DB를 보존하는 `risk_events` additive schema migration 및 CRUD 추가.
- `tests/test_risk_guard.py`, `tests/test_engine_risk_priority.py`, `tests/test_risk_event_recovery.py`: 판정·우선순위·중복/복구 검증.

브로커 transport 파일은 수정하지 않았고 live 실행도 하지 않았다.

## 검증

- Python syntax compile: `syntax ok`
- 순수/SQLite 테스트 직접 실행: `risk tests ok`
- `git diff --check`: 통과
- 지정 pytest 명령: 실행 불가 — 현재 기본 Python 환경에 `pytest`가 설치되어 있지 않음.
- priority 테스트 직접 실행: 실행 불가 — 현재 기본 Python 3.8이 기존 `risk_manager.py`의 `tuple[...]` 타입 힌트를 import하지 못함. 프로젝트의 호환 Python/`.venv`에서 재실행 필요.

## 남은 위험

- 실제 브로커 연결·주문은 검증하지 않았다.
- risk 주문의 timeout/cancel 재시도는 기존 미체결 관리와 완전한 risk 전용 상태 머신으로 분리하는 후속 검토가 필요하다.
- `.venv` 또는 Python 3.10+ 환경에서 전체 acceptance pytest를 반드시 재실행해야 한다.
