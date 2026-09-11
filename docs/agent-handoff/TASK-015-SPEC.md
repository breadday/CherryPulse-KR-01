# TASK-015 SPEC

## Goal

paper trading 또는 live 주문 비허용 상태에서 Kiwoom `SendOrder` 경로가 호출되지 않는다는 회귀 증거를 추가한다.

## Scope

- `KiwoomBroker.place_order()`의 매수·매도 차단을 검증한다.
- `KiwoomBroker.cancel_order()`의 취소 차단을 검증한다.
- `PAPER_TRADING`과 `ALLOW_LIVE_ORDERS`의 모든 차단 조합을 검증한다.

## Safety constraints

- production 코드와 거래 설정은 변경하지 않는다.
- PyQt5 ActiveX 객체를 생성하지 않는다.
- Kiwoom COM과 실제 주문 API를 호출하지 않는다.
- 테스트의 `_send_order_with_retry`는 호출 기록용 trap으로 대체한다.

## Acceptance criteria

- paper trading이 켜져 있으면 live 허용값과 관계없이 주문·취소 전송 호출이 0회다.
- paper trading이 꺼져 있어도 live 주문 허용값이 false이면 주문·취소 전송 호출이 0회다.
- 매수와 매도 모두 모의 `SUBMITTED` 주문을 반환한다.
- 전체 pytest가 Python 3.10 32비트에서 통과한다.
