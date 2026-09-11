# TASK-021 SPEC

## Goal

Kiwoom TR·조건검색 요청에 공통 사용되는 event-loop timeout helper가 대기 종료와 cleanup을 정확히 수행하는지 stub 회귀 테스트로 고정한다.

## Scope

- timeout callback이 실행 중인 loop를 한 번 종료하는지 검증한다.
- 최소 timeout 1000ms와 요청 label 로그를 검증한다.
- 정상 event-loop 완료가 timeout으로 오인되지 않는지 검증한다.
- callback 전에 loop reference가 교체되면 이전 loop와 새 loop를 건드리지 않는지 검증한다.
- loop가 없으면 timer를 생성하지 않고 false를 반환하는지 검증한다.

## Safety constraints

- `broker/kiwoom_broker.py`와 production 코드를 변경하지 않는다.
- QTimer, QEventLoop, QAxWidget은 stub만 사용한다.
- Kiwoom COM, 로그인, TR, 조건검색, 계좌, 주문 API를 실제 호출하지 않는다.

## Acceptance criteria

- timeout 시 return value가 true이고 loop quit가 정확히 1회다.
- 정상 완료, 교체된 loop, 없는 loop는 false를 반환한다.
- 생성된 timer는 성공·timeout 경로 모두 stop/delete cleanup된다.
- Python 3.8 단독 실행은 정상 skip되고 Python 3.10에서 모든 focused test가 통과한다.
- 전체 pytest가 통과한다.
