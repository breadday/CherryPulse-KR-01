# TASK-004 구현 보고서

## 변경 파일

- `engine.py`: 손절 주문 dispatcher를 일반 매도 경로와 분리하고, broker 미체결 대조·취소 확인 timeout·fail-closed manual intervention·risk-only retry를 보강했다. heartbeat/shutdown에서 durable risk 상태를 관찰한다.
- `main_live.py`: 장외 및 장마감 경계에서도 risk 상태를 관찰하고, 종료 전에 bounded 계좌/미체결 대조를 시도한다. stale 데이터로 신규 stop을 만들지 않는다.
- `tests/test_risk_sell_state_machine.py`: 취소 확인 timeout과 pending partial 복구/중복 재주문 방지 테스트를 추가했다.

## 검증

- `python -m pytest -q` — **8 passed**
- Python compile check (`core/models.py`, `core/risk_guard.py`, `core/order_manager.py`, `engine.py`, `infra/sqlite_store.py`, `main_live.py`) — **syntax ok**
- `git diff --check` — 공백 오류 없음 (기존 줄바꿈 경고만 출력)

## 남은 위험

- 키움 COM, live broker, 실계좌는 실행하지 않았다. 실제 broker의 pending 응답 필드와 취소 상태 의미는 모의투자 로그로 추가 확인해야 한다.
- 작업 트리에 TASK-003 이전 변경사항이 함께 존재하므로 해당 변경들은 되돌리지 않았다.
