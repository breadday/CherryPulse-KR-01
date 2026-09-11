# TASK-003 구현 보고서

## 발견한 원인

손절 주문이 일반 매도 timeout/cancel/retry 상태와 동일한 조회 경로를 사용했고, 취소 요청 접수만으로 취소 완료를 확정했습니다. 재시작 시 durable risk event와 broker 미체결 대조도 충분하지 않았습니다.

## 변경 내용

- `engine.py`: risk 주문 metadata/context, 유한 risk timeout·취소·재주문 상태 처리, 일반 매도 dispatcher 분리, broker 미체결 재조정 및 재시작 보수 복구를 추가했습니다.
- `core/risk_guard.py`: terminal/open 상태 판정과 storage 오류 전파를 보강했습니다.
- `infra/sqlite_store.py`: additive 취소/최근 action timestamp 컬럼, 원자적 risk event 갱신 허용 필드, 수동개입 상태 자동조회 제외를 추가했습니다.
- `tests/test_risk_sell_state_machine.py`: 거부 terminal 처리와 취소 확인 전 재주문 금지/확인 후 risk-only 재주문을 추가했습니다.

기존 일반 매도 조건과 broker transport 호출부는 변경하지 않았습니다. 실제 키움 계좌와 live 실행은 수행하지 않았습니다.

## 검증

- `python -m pytest -q` → `6 passed`
- Python compile check (`core/risk_guard.py`, `engine.py`, `infra/sqlite_store.py`) → `syntax ok`
- `git diff --check` → 통과

## 남은 위험

실제 broker의 취소 확정/계좌 대조는 fake broker로 검증하지 못했습니다. broker pending 조회가 실패하면 자동 재주문하지 않고 수동개입으로 남기는 보수 경로이며, 실제 키움 COM 연결은 별도 모의투자 운영 검증이 필요합니다.
