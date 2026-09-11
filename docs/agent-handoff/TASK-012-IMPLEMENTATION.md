# TASK-012 구현 보고서

## 발견한 원인

`_submit_risk_sell()`가 새 주문을 `OrderManager`와 `risk_order_events`에 등록한 뒤 binding snapshot을 만들고 있었다. 기존 broker ID 충돌로 binding이 실패하면 snapshot 자체에 신규 local order가 포함되어 rollback 뒤에도 미확인 주문이 남았다.

## 변경 내용

- 신규 order와 risk mapping을 등록하기 전에 OrderManager orders, 양방향 mapping, 기존 broker ID field, risk event map을 snapshot한다.
- broker identity가 missing/ambiguous/conflicting이면 snapshot을 복원하고 신규 자동 후속 action을 차단한다.
- TASK-012 테스트를 추가해 세 가지 실패 경로를 고정했다.

## 안전성

실제 broker transport, Kiwoom/COM, 주문 제출, `.env`, live enablement, 전략 코드는 실행하거나 수정하지 않았다. 커밋·push·merge는 수행하지 않았다.
