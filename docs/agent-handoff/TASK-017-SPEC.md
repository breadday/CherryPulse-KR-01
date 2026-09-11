# TASK-017 SPEC

## Goal

전략별 snapshot·조건검색 유니버스가 서로 오염되지 않고 독립적으로 갱신되는지 자동 회귀 테스트로 고정한다.

## Scope

- snapshot의 전략 태그별 후보 분리를 검증한다.
- 조건검색 후보가 허용된 전략에만 들어가는지 검증한다.
- 조건검색에서 제거된 종목의 snapshot 소속이 유지되는지 검증한다.
- snapshot 교체가 이전 snapshot 소속만 제거하고 조건검색 소속은 유지하는지 검증한다.
- selector universe name 매핑과 보유·미체결 종목 라우팅을 검증한다.

## Safety constraints

- production 코드, 전략 설정, 주문, broker transport, `.env`, live 활성화를 변경하지 않는다.
- 파일 기반 snapshot, Kiwoom, COM, 계좌 또는 주문 API를 실행하지 않는다.
- 테스트는 메모리 내 `UniverseManager` 상태만 사용한다.

## Acceptance criteria

- bottom, leader, close-buy snapshot 후보가 태그대로 분리된다.
- momentum 조건검색 후보가 snapshot 전용 전략으로 유출되지 않는다.
- 한 source의 제거·교체가 다른 source의 소속을 삭제하지 않는다.
- 알 수 없는 strategy/universe 이름은 fail-closed로 빈 결과 또는 false를 반환한다.
- 전체 pytest가 Python 3.10 32비트에서 통과한다.
