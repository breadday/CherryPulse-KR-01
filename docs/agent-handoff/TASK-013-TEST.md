# TASK-013 테스트 보고서

## 관련 테스트

`python -m pytest -q tests/test_task013_fill_isolation.py tests/test_task011_recovery_isolation.py`

결과: `15 passed in 0.87s`

## 확인 항목

- A cumulative fill `40, 40, 60`의 중복 40 무시와 최종 100 체결
- A position 0 및 risk event `CLOSED`
- B position 100, fill 0, risk event `SELL_SUBMITTING` 유지
- account query exception 이후 A/B durable event 전체 필드 불변
- shutdown 이후 heartbeat 3회에서 observation/pending 호출 0회

실제 broker/COM/주문 경로는 실행하지 않았다.
