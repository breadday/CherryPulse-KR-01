# TASK-007 구현 보고서 — 주문 identity/type 계약 보완

상태: `IMPLEMENTED`

## 변경 파일

- `core/models.py`: `Order`에 `purpose`, `risk_event_id`, `broker_order_id` 정식 필드를 추가했다. 기존 positional 생성 순서는 유지했다.
- `core/order_manager.py`: local↔broker 양방향 mapping, 충돌 검증 binding, 엄격한 broker 조회, event 기준 risk SELL 조회를 추가했다.
- `engine.py`: risk submit/reconcile/sync/cancel/fill 경로가 명시적 identity API를 사용하도록 보완했다. 미확정 identity와 잘못된 pending 수량은 manual fail-closed하며 local ID를 broker ID로 fallback하지 않는다. 누적 fill은 delta만 반영하고 position zero는 `CLOSED`로 기록한다.
- `tests/test_risk_sell_state_machine.py`: cumulative/duplicate fill 및 unknown fill 차단 테스트를 추가했다.
- `tests/test_risk_restart_reconcile.py`: identity binding/query 계약 테스트를 추가했다.

broker transport, `main_live.py`, SQLite schema는 수정하지 않았고 live/COM 실행도 하지 않았다.

## 검증

- `python -m pytest -q` → **13 passed** (기존 8개 + 신규/보강 5개)
- Python syntax compile (`core/models.py`, `core/order_manager.py`, `engine.py`) → **syntax ok**
- `git diff --check` → **통과** (기존 CRLF 경고만 표시)

fake broker 기준 failure-path 자동 주문 결과:

- cancel confirmation 전 대기 및 timeout disappearance: 추가 `place_order=0`, 추가 `cancel_order=0`
- reject/manual, unknown fill, duplicate cumulative fill: 자동 추가 주문/취소 `0회`
- 정상 stop submit 자체는 `place_order=1`; pending identity가 유효하지 않으면 그 뒤 추가 place/cancel `0회`

## 남은 위험

- 실제 키움 pending/account 응답과 네트워크 장애 조합은 fake broker 테스트로만 검증했다. 배포 전 SQLite event/order와 broker pending/보유잔고를 수동 대조해야 한다.
- 작업 트리에 TASK-007과 무관한 기존 변경이 존재하므로 정리하거나 되돌리지 않았다. 실계좌 가능 환경에서는 identity manual 상태를 해소하기 전 자동 주문을 재개하지 말아야 한다.
