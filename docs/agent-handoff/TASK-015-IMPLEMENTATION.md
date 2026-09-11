# TASK-015 IMPLEMENTATION

## Changed files

- `tests/test_task015_paper_order_block.py`
  - 실제 broker 모듈을 별도 module name으로 로드해 다른 테스트의 module stub과 격리했다.
  - PyQt5와 QAxWidget은 import 전용 stub으로 대체했다.
  - `_send_order_with_retry`를 호출 기록용 trap으로 대체하고 주문·취소 전송이 0회인지 검증한다.
  - 매수·매도와 세 가지 차단 플래그 조합을 검증한다.
- `docs/agent-handoff/TASK-015-SPEC.md`
  - paper 주문 차단의 테스트 계약과 안전 제약을 기록했다.

## Production impact

- production 코드는 변경하지 않았다.
- 거래 설정과 주문 처리 동작은 변경하지 않았다.
- CI 전체 테스트 수는 59개에서 68개로 증가한다.

## Safety

- `KiwoomBroker.__init__()`을 호출하지 않아 QAxWidget 또는 COM 객체가 생성되지 않는다.
- 실제 `_send_order_with_retry()` 구현은 테스트에서 호출되지 않는다.
- `.env`, 계좌 연결, broker transport, live trading 활성화는 변경하거나 실행하지 않았다.
