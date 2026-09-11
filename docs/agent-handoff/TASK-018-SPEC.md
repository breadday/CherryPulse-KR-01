# TASK-018 SPEC

## Goal

일일 손실 한도와 전략별 연속손실 보호가 신규 진입을 차단하면서 독립적인 stop-loss 위험청산은 계속 허용하는 우선순위를 회귀 테스트로 고정한다.

## Scope

- 일일 실현손익이 당일 기준값을 빼고 계산되는지 검증한다.
- 일일 손실 한도 도달 시 신규 BUY가 차단되는지 검증한다.
- 한 전략의 연속손실이 다른 전략이나 전체 엔진을 보호모드로 전환하지 않는지 검증한다.
- 전체 엔진 보호모드에서도 독립 risk guard가 stop 주문을 제출하는지 검증한다.

## Safety constraints

- production 코드와 설정을 변경하지 않는다.
- broker는 메모리 stub만 사용한다.
- Kiwoom, COM, 계좌, 네트워크, 실제 주문 API를 실행하지 않는다.

## Acceptance criteria

- 당일 손익은 누적 실현손익에서 `daily_realized_pnl_base`를 뺀 값이다.
- 일일 손실 한도 경계값에서도 신규 BUY가 차단된다.
- 전략 연속손실 보호는 해당 전략에만 적용된다.
- `engine_protected=true` 상태에서도 보유 포지션의 stop-loss SELL은 한 번 제출된다.
- stop-loss 처리 시 strategy와 외부 데이터 경로는 실행되지 않는다.
- 전체 pytest가 통과한다.
