# TASK-009 구현 보고서

## 변경 내용

- `main_live.py`
  - heartbeat에서 `auto_shutdown()`을 리스크/미체결 관리보다 먼저 실행하도록 순서를 변경했다.
  - 15:35 이상 heartbeat는 즉시 반환하며 recovery/order management를 시작하지 않는다.
  - shutdown 진입 즉시 `engine.request_shutdown()`을 호출한다.
  - 14:40/15:20 독립 recovery cutoff 없이 15:35 경계만 유지한다.
- `engine.py`
  - `shutdown_requested` fail-closed gate를 추가하고 신규 place/cancel, retry, stale 취소를 차단했다.
  - risk sell binding 실패 시 local order, 양방향 mapping, in-memory risk map, `sell_in_progress`를 복구하고 durable event만 수동개입 상태로 남긴다. broker 주문을 취소하거나 재전송하지 않는다.
  - pending/account 오류의 전역 manualization을 제거하고 event identity 기준으로 수동개입을 격리했다. event별 reconciliation 예외도 다음 event 처리를 중단하지 않는다.
- `tests/test_risk_restart_reconcile.py`, `tests/test_risk_sell_state_machine.py`
  - event 격리 및 shutdown 이후 broker action 0회 불변조건을 고정했다.

## 검증

- 문법 검사: `main_live.py`, `engine.py`, `core/order_manager.py` 통과 (`syntax ok`)
- 전체 테스트: **16 passed**
- shutdown gate 테스트: fake broker `place_order=0`, `cancel_order=0`
- 기존 recovery/risk restart 테스트 및 누적 체결 테스트 통과
- `git diff --check`: 기존 작업 트리의 agent log 파일 trailing whitespace로 경고/실패. 해당 무관한 로그는 수정하지 않았다.

## 경계별 결과

- 14:40: 독립 reconnect 차단 없음
- 15:20: 독립 stale recovery 차단 없음
- 15:35: shutdown 선행 및 신규 recovery/place/cancel 차단

## 남은 위험

- 실제 키움 계좌/COM 연결은 실행하지 않았다. binding 실패로 수동개입 상태가 된 broker 주문은 배포 전 broker 화면과 SQLite를 수동 대조해야 한다.
- 현재 작업 트리에 TASK-009와 무관한 기존 변경 및 로그 파일이 있으므로 커밋/정리는 수행하지 않았다.
