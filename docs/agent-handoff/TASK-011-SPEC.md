# TASK-011 구현 명세 — recovery 경계 및 risk event 오류 격리

상태: `IMPLEMENTATION_CONTRACT`

## 목표

TASK-009 Review에서 남은 안전 경계를 테스트로 고정하고, broker pending 조회 계층의 일시적 실패가 서로 다른 risk event의 상태를 오염시키지 않도록 수정한다.

## 범위

- `engine.py`: `_reconcile_risk_event()`의 pending 조회 예외 처리
- `tests/test_task011_recovery_isolation.py`: recovery 시간 경계, heartbeat/shutdown 순서, event 격리 테스트
- 현재 TASK handoff 문서

다음은 수정·실행하지 않는다.

- `broker/kiwoom_broker.py`, Kiwoom/COM, 실제 주문·체결
- `.env`, live trading 활성화, SQLite schema/API
- 전략·후보선정 로직

## 구현 계약

1. `14:39`, `14:40`, `14:41`, `15:19`, `15:20`, `15:21`, `15:34`에는 기존 recovery 조건이 허용하는 한 broker recovery를 시도할 수 있다.
2. `15:35`, `15:36`에는 직접 recovery 호출도 broker reconnect를 시작하지 않는다.
3. heartbeat는 `auto_shutdown()`을 risk observation/pending management보다 먼저 호출한다.
4. shutdown은 engine action gate를 설정한 뒤 종료 전 reconciliation을 호출한다.
5. pending query 자체가 실패하면 특정 event의 identity 오류로 간주하지 않고 해당 durable event 상태를 변경하지 않는다. 이 경로에서 place/cancel은 발생하지 않는다.

## 검증

```powershell
python -m pytest -q tests/test_task011_recovery_isolation.py
python -m pytest -q
python -B -c "from pathlib import Path; files=['engine.py','tests/test_task011_recovery_isolation.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
git diff --check -- engine.py
```

실제 broker 연결과 주문 API는 테스트하지 않는다.
