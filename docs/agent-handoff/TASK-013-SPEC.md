# TASK-013 구현 명세 — 체결·조회·shutdown 이벤트 격리

상태: `IMPLEMENTATION_CONTRACT`

## 목표

TASK-009 Review의 마지막 미검증 경계를 자동 테스트로 고정한다.

- 서로 다른 risk event A/B 사이의 누적 체결 격리
- account query exception 시 durable risk event 보존
- shutdown 이후 반복 heartbeat에서 observation/pending work 재시작 차단

## 범위

- `tests/test_task013_fill_isolation.py`
- `tests/test_task011_recovery_isolation.py`의 반복 heartbeat 회귀 테스트
- TASK-013 handoff 문서

production code, broker transport, `.env`, live enablement, SQLite schema/API, 전략 코드는 수정하지 않는다. 실제 Kiwoom/COM과 주문 API는 실행하지 않는다.

## acceptance

1. A event의 cumulative fill `40, 40, 60`에서 duplicate 40은 한 번만 반영되고 A만 종료된다.
2. B position, order fill, durable event state는 A 체결의 영향을 받지 않는다.
3. account query exception은 A/B event를 변경하지 않고 호출자에게 전파된다.
4. shutdown 상태의 heartbeat를 반복 호출해도 risk observation과 pending management를 시작하지 않는다.

## 검증

```powershell
python -m pytest -q tests/test_task013_fill_isolation.py tests/test_task011_recovery_isolation.py
python -m pytest -q
```
