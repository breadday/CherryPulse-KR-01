# TASK-008 테스트 보고서

## 실행 결과

### 1. TASK-008 관련 좁은 테스트

명령:

```powershell
python -m pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_restart_reconcile.py
```

결과: **통과** — `10 passed in 1.40s`

검증된 주요 경로:

- risk stop 상태 머신 및 누적 체결 idempotency
- pending 주문 재조정 시 재주문 방지
- cancel confirmation timeout fail-closed
- SQLite risk event 기반 binding 실패 rollback
- binding 실패 시 `place_order=0`, `cancel_order=0`

### 2. 전체 pytest suite

명령:

```powershell
python -m pytest -q
```

결과: **통과** — `14 passed in 1.70s`

### 3. 정적 검증

명령:

```powershell
python -B -c "from pathlib import Path; files=['main_live.py','engine.py','core/order_manager.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
```

결과: **통과** — `syntax ok`

명령:

```powershell
```

결과: **통과**. Git이 기존 변경 파일의 LF→CRLF 변환 가능성 경고만 출력했으며 diff whitespace 오류는 없었다.

## 누락/제한된 coverage

- `tests/`에는 `main_live.py` recovery-window 테스트가 없어 14:39/14:40/14:41, 15:19/15:20/15:21, 15:34, 15:35/15:36 및 heartbeat shutdown 선행 순서를 직접 검증하지 못했다.
- 전체 suite는 현재 14개 테스트만 수집했다. 명세의 새 `TradingEngine` restart end-to-end 시나리오(동일 DB로 새 engine 생성, account/pending 예외, missing/ambiguous identity, cumulative 40→40→60 fill 전체)는 모두 독립 테스트로 완성되어 있지 않다.
- PyQt5/실제 QApplication·Kiwoom 연결 테스트는 실행하지 않았다. live 주문 및 COM 연결은 실행하지 않았다.

## 안전 확인

- 테스트는 fake broker와 temporary SQLite만 사용했으며 실제 주문을 실행하지 않았다.
- 현재 tracked diff 목록에는 `broker/kiwoom_broker.py`, `.env`가 포함되지 않았다. 작업 트리에는 TASK-007 및 기타 무관한 기존 변경이 있어 이를 되돌리지 않았다.

## 판정

현재 구현은 좁은 risk 테스트, 전체 pytest, syntax 및 diff 검사를 통과했다. 다만 TASK-008 명세의 `main_live` 시간 경계와 일부 restart/예외 acceptance coverage가 실제 테스트로 확보되지 않아, 해당 부분은 **미검증**으로 남긴다.
