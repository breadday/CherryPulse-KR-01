# TASK-016 IMPLEMENTATION

## Changed files

- `validate_daily_snapshot.py`
  - 과거 `generated_at`을 허용하고 미래 생성일만 거부하도록 수정했다.
  - `latest_data_date`가 오늘보다 미래이면 명시적으로 거부한다.
- `main_live.py`
  - 실제 snapshot 로드 경로에 동일한 생성일·미래 일봉 정책을 적용했다.
- `tests/test_task016_snapshot_calendar.py`
  - CLI validator와 앱 validator를 같은 payload와 고정 시각으로 검증한다.
  - 금요일→월요일, 금요일→월요일 휴장→화요일, 실제 개장일 누락, 미래 생성일, 미래 일봉을 포함한다.
- `docs/agent-handoff/TASK-016-SPEC.md`
  - 거래일 기준 snapshot 최신성 계약을 기록했다.

## Behavior

- 장 마감 후 생성한 snapshot은 주말과 설정된 휴장일을 지나 다음 거래일에 사용할 수 있다.
- 개장일 데이터가 실제로 누락되면 기존처럼 fail-closed 처리한다.
- 미래 생성일과 미래 일봉 데이터는 fail-closed 처리한다.

## Safety

- 전략, 주문, broker transport, 계좌 설정, `.env`, live 활성화를 변경하지 않았다.
- 검증은 임시 snapshot JSON과 stubbed UI/broker module만 사용했다.
- Kiwoom COM 또는 주문 API를 호출하지 않았다.
