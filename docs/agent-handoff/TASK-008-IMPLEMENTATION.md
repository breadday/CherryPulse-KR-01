# TASK-008 구현 보고서

## 발견한 원인

- `main_live.py`가 14:40 이후 reconnect와 15:20 이후 stale-realdata recovery를 차단해 15:35 자동 종료 전 보유 포지션 감시 공백이 생겼다.
- `sync_pending_orders()`가 broker ID binding 전에 local 주문과 risk mapping을 등록해 binding 실패 시 부분 상태가 남을 수 있었다.

## 변경 파일

- `main_live.py`: 14:40/15:20 독립 cutoff를 제거하고 `AUTO_SHUTDOWN_HHMM`(15:35) 미만까지 recovery를 허용했다. 15:35 이상 direct recovery도 fail-closed로 차단한다.
- `engine.py`: pending item identity/수량 검증을 보강하고, binding 실패 시 orders·양방향 mapping·order broker field·`risk_order_events`를 호출 전 상태로 rollback한다. 성공 후에만 risk mapping을 기록한다.
- `tests/test_risk_restart_reconcile.py`: 실제 temporary SQLite risk event와 `TradingEngine`을 사용하는 binding 실패 rollback 테스트를 추가했다. place/cancel 호출은 모두 0회인지 검증한다.

## 검증

- Python syntax compile (`main_live.py`, `engine.py`, `core/order_manager.py`): 통과
- `PYTHONPATH=. pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_restart_reconcile.py`: **10 passed**
- `git diff --check`: 통과
- 전체 `pytest -q`: 120초 제한으로 `..........` 출력 후 완료하지 못함

## 남은 위험

- 이 환경에는 PyQt5가 없어 `main_live` 실제 QApplication/키움 연결 테스트는 실행하지 못했다. live 주문은 실행하지 않았다.
- 전체 테스트 완료 증거가 없으므로 배포 전 전체 suite를 충분한 timeout으로 재실행해야 한다.
- 기존 작업 트리의 TASK-007 및 기타 무관한 변경은 명세에 따라 되돌리지 않았다.
