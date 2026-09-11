# TASK-002 구현 보고서

## 변경 내용

- `core/risk_manager.py`
  - `typing.Tuple`을 추가하고 `RiskManager.can_trade` 반환 표기를 `Tuple[bool, str]`로 변경했다.
- `engine.py`
  - `typing.Dict`, `List`, `Tuple`을 추가했다.
  - 명세의 네 반환 타입 표기를 Python 3.8 호환 표기로 변경했다.

매매 조건, 손절 판정, 주문 우선순위, RiskGuard 상태 전이, SQLite 로직, 브로커 transport는 변경하지 않았다. 작업 전부터 존재한 TASK-001 관련 변경은 유지했다.

## 검증

- `python --version` → `Python 3.8.10`
- RiskGuard 및 `TradingEngine` import → `py38 imports ok`
- 지정 production 파일 문법 검사 → `syntax ok`
- `python -m pytest -q` → `4 passed in 0.36s`
- `git diff --check` → 통과(줄바꿈 형식 경고만 출력)
- live 실행 및 키움 연결 → 실행하지 않음

## 남은 위험

Python 3.8 호환 타입 표기만 수정했으며, 실계좌 주문 경로는 검증하지 않았다. 저장소에는 TASK-001의 기존 미커밋 변경이 함께 남아 있다.
