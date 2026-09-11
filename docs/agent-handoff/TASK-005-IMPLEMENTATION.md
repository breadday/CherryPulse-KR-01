# TASK-005 구현 보고서

## 변경 내용

- `engine.py`
  - 손절 주문 제출 시 local 주문 ID와 broker 주문 ID를 분리하고, local ID를 broker ID로 대체하지 않도록 수정했다.
  - 제출 직후 pending 조회에서 broker 주문번호가 정확히 하나로 확인될 때만 binding한다. 조회 실패, 빈/복수 후보, local ID 반환은 `MANUAL_INTERVENTION_REQUIRED`로 종료한다.
  - broker ID가 확정되지 않은 손절 주문은 취소·재주문하지 않는다.
  - `CANCEL_REQUESTED` 주문은 확인 timeout 전 pending 부재만으로 retry하지 않으며, timeout 후 확정 대조 실패는 manual로 종료한다.
  - 계좌/pending 동기화 예외를 빈 성공값으로 변환하지 않고 열린 risk event를 manual 상태로 기록한 뒤 예외를 전파한다.
- `infra/sqlite_store.py`
  - risk event update가 실제 행을 갱신하지 못하거나 갱신 후 조회되지 않으면 예외를 발생시켜 fail-closed 처리한다.
- `main_live.py`
  - heartbeat에서 risk 관찰을 auto-shutdown보다 먼저 수행한다.
  - shutdown의 risk observation, pending sync, account sync를 독립적으로 시도한다.

## 검증

- Python compile check: 통과
- `git diff --check`: 통과
- `python -m pytest -q`: 6 passed, 2 failed

기존 `tests/test_risk_sell_state_machine.py`의 두 실패는 fake broker가 pending 조회에서 broker 번호를 제공하지 않는데도 기존 동작(`cancel` 및 자동 retry)을 기대하기 때문이다. TASK-005 명세의 fail-closed 요구와 충돌한다.

## 남은 위험

- 명세가 요구한 `core/models.py`의 정식 dataclass 필드 및 `core/order_manager.py`의 risk 전용 helper, 재시작/장마감 신규 테스트는 이번 변경에 포함되지 않았다.
- broker 번호 binding 이후의 완전한 partial-fill/restart matrix와 bounded timeout은 추가 구현 및 fake-clock 테스트가 필요하다.
- live 실행, 키움 COM, 실주문은 실행하지 않았다.
