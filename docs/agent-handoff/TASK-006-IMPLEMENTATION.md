# TASK-006 구현 보고서

## 변경 파일

- `engine.py`: `_check_stale_risk_order`의 broker ID 검사를 실행 가능한 위치로 이동해 확정된 broker 주문번호로만 timeout cancel하도록 유지했다.
- `tests/test_risk_sell_state_machine.py`: local ID와 별도 broker ID를 사용하는 fake pending fixture로 갱신하고, cancel confirmation 전 disappearance 시 재주문하지 않는 계약을 반영했다.

## 검증

- `python -m pytest -q`: **8 passed**
- Python compile check (`core/models.py`, `core/order_manager.py`, `engine.py`): 통과
- `git diff --check`: 통과

## 알려진 위험 / 미완료

현재 작업공간 편집 정책이 `core/models.py`와 `core/order_manager.py` 수정을 거부하여 명세의 정식 `Order` risk 필드, 명시적 양방향 binding API, broker ID 기반 fill/restart 매핑은 구현하지 못했다. 따라서 TASK-006 전체 acceptance를 충족했다고 볼 수 없다. pending/account 예외와 live broker/COM은 실행하지 않았다.
