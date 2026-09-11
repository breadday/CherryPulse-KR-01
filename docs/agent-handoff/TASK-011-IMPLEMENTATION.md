# TASK-011 구현 보고서

## 발견한 원인

`TradingEngine._reconcile_risk_event()`가 `get_pending_orders()` 예외를 해당 risk event의 `MANUAL_INTERVENTION_REQUIRED`로 기록했다. `sync_pending_orders()`가 여러 open event를 순서대로 재조정하므로, 공유 pending 조회 장애 하나가 A/B를 모두 수동개입 상태로 만들 수 있었다.

## 변경 내용

- pending query 예외 시 event 상태와 durable identity를 변경하지 않고 warning을 남긴 뒤 `False`를 반환하도록 수정했다.
- `tests/test_task011_recovery_isolation.py`를 추가했다.
  - 14:39~15:34 recovery 허용 경계
  - 15:35/15:36 direct recovery 차단
  - heartbeat의 shutdown 선행 순서
  - shutdown gate 이후 reconciliation 순서
  - pending query failure의 A/B event 격리

## 안전성

실제 broker transport, Kiwoom/COM, 주문 제출, `.env`, live enablement, 전략 코드는 실행하거나 수정하지 않았다. 커밋·push·merge도 수행하지 않았다.
