# TASK-012 구현 명세 — risk sell broker identity rollback

상태: `IMPLEMENTATION_CONTRACT`

## 목표

TASK-009 Review에 남은 `_submit_risk_sell()` broker ID binding failure acceptance를 닫는다. broker 주문이 이미 제출된 뒤 identity를 확정하지 못하면 자동 cancel/re-submit 없이 local 상태와 mapping을 제출 전으로 복원하고 durable risk event만 수동개입 상태로 남긴다.

## 범위

- `engine.py`: `_submit_risk_sell()`의 binding 전 snapshot과 rollback
- `tests/test_task012_binding_failure.py`: missing, ambiguous, existing broker identity conflict 경로
- TASK-012 handoff 문서

broker transport, `.env`, live enablement, SQLite schema/API, 전략 코드는 수정하지 않는다. 실제 Kiwoom/COM과 주문 API는 실행하지 않는다.

## 구현 계약

1. broker `place_order()`가 성공한 뒤 pending broker ID가 없거나 여러 개면 자동 cancel/re-submit하지 않는다.
2. 기존 broker ID와 충돌하면 신규 local order, 양방향 mapping, `risk_order_events`, `sell_in_progress`를 제출 전 상태로 복원한다.
3. durable risk event는 삭제하지 않고 `MANUAL_INTERVENTION_REQUIRED`로 기록하며 local/broker identity를 비운다.
4. binding failure에서 `place_calls == 1`, `cancel_calls == 0`이어야 한다.

## 검증

```powershell
python -m pytest -q tests/test_task012_binding_failure.py
python -m pytest -q
python -B -c "from pathlib import Path; files=['engine.py','tests/test_task012_binding_failure.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
git diff --check -- engine.py
```
