# TASK-007 테스트 보고서

상태: `PASS`

## 실행 결과

작업 트리의 기존 변경은 유지했으며, production code는 수정하지 않았다.

1. 관련 테스트

   ```powershell
   python -m pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_restart_reconcile.py
   ```

   결과: **9 passed in 1.08s**

2. 전체 테스트

   ```powershell
   python -m pytest -q
   ```

   결과: **13 passed in 1.29s**

3. 구현 대상 syntax compile

   ```powershell
   python -B -c "from pathlib import Path; files=['core/models.py','core/order_manager.py','engine.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
   ```

   결과: **syntax ok**

4. diff 검사

   ```powershell
   git diff --check
   ```

   결과: **통과**. Git의 기존 LF/CRLF 변환 경고만 출력되었고 whitespace error는 없었다.

## 검증 범위

- `Order`의 formal risk identity 필드 및 local↔broker binding 계약
- 빈 값, unknown local, 동일 ID, event mismatch identity의 fail-closed 동작
- risk event 기준 단일 open SELL 조회 및 중복 후보 거부
- timeout cancel 후 `CANCEL_REQUESTED` 유지와 confirmation 전 재주문 방지
- pending partial 40/100 및 잔량 60 보존
- cumulative/duplicate fill의 delta 반영과 terminal `CLOSED` 전이
- unknown fill의 order/portfolio 변경 차단
- reject/manual 상태의 재시도 차단

## 자동 주문 호출 횟수

실패 경로 테스트에서 추가 자동 주문은 모두 `place_order=0`, `cancel_order=0`으로 확인되었다.
정상 stop submit 자체는 `place_order=1`이며, 이후 pending identity가 유효하지 않은 경우 추가 `place_order=0`, `cancel_order=0`이다.

## 누락된 coverage / 제한

- 전체 테스트는 13개이며, 실제 키움 OpenAPI/COM transport, 네트워크 장애, live 계좌는 실행하지 않았다.
- SQLite 재시작 후 실제 `TradingEngine`을 새로 생성하는 end-to-end recovery와 pending/account 조회 예외의 모든 조합은 현재 테스트에 직접 포함되지 않았다.
- `main_live.py` 실행, 실 broker pending/account 응답, 배포 전 broker와 SQLite 상태의 수동 대조는 별도 운영 검증이 필요하다.
