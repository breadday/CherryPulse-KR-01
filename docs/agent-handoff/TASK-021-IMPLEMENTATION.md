# TASK-021 IMPLEMENTATION

## Changed files

- `tests/test_task021_broker_timeout.py`
  - broker module을 별도 module name과 PyQt import stub으로 로드한다.
  - fake timer와 fake event loop로 timeout·정상 완료·loop 교체·loop 없음·로그인 timeout 경계를 검증한다.
  - timeout 최소값, warning label, quit 횟수, timer cleanup을 검증한다.
- `broker/kiwoom_broker.py`, `config_live.py`
  - 로그인 이벤트 대기에 `KIWOOM_LOGIN_TIMEOUT_SEC` 기반 공통 timeout을 적용한다.
- `docs/agent-handoff/TASK-021-SPEC.md`
  - 공통 broker event-loop timeout 계약과 안전 제약을 기록했다.

## Result

- 현재 `_exec_loop_with_timeout()` 구현은 검증한 다섯 경계에서 정상 동작했다.
- 로그인 이벤트가 누락되면 계좌/TR 조회로 진행하지 않고 제한시간 초과 예외로 종료한다.
- 전체 회귀 테스트는 `111 passed, 18 skipped`로 확인했다.

## Safety

- `KiwoomBroker.__init__()`을 호출하지 않았다.
- QTimer, QEventLoop, QAxWidget은 import 또는 동작 stub만 사용했다.
- Kiwoom COM, 로그인, TR, 조건검색, 계좌, 주문 API를 실제 호출하지 않았다.
