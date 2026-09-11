# TASK-016 SPEC

## Goal

전 거래일 장 마감 후 만든 일봉 snapshot이 주말·휴장일을 지나 다음 거래일에 정상 사용되도록 최신성 정책을 수정한다.

## Scope

- standalone `validate_daily_snapshot.py`와 `MainLiveApp`의 정책을 동일하게 유지한다.
- `generated_at`은 과거 생성일을 허용하되 미래 생성일은 차단한다.
- `latest_data_date`를 거래일 최신성의 기준으로 사용한다.
- 주말과 `MARKET_HOLIDAYS`는 누락 거래일로 계산하지 않는다.
- 실제 장이 열린 날의 데이터 누락과 미래 일봉은 차단한다.

## Safety constraints

- 전략, 주문, broker transport, 계좌, `.env`, live 활성화를 변경하지 않는다.
- snapshot 파일을 생성하거나 운영 데이터를 수정하지 않는다.
- 모든 검증은 임시 JSON과 고정 시각을 사용한다.

## Acceptance criteria

- 금요일 snapshot은 월요일에 유효하다.
- 금요일 snapshot은 월요일 휴장 후 화요일에 유효하다.
- 월요일이 장이 열린 날이면 금요일 snapshot은 화요일에 거부된다.
- 미래 `generated_at`과 미래 `latest_data_date`는 거부된다.
- CLI validator와 앱 validator가 모든 사례에서 같은 판정을 낸다.
