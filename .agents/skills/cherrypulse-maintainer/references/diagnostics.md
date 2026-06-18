# 진단 기준

## 우선 확인 순서

1. `logs/trading.log`의 최신 기록 시각
2. `%LOCALAPPDATA%/CherryPulse-KR-01/cherry_pulse.sqlite3`
3. `condition_snapshot.json`의 생성일과 `latest_data_date`
4. 계좌 동기화의 positions, pending_orders, deposit
5. 전략별 universe 수와 실시간 구독 종목

## SQLite 핵심 테이블

- `signals`: 전략 신호, 허용 여부, 차단 사유와 시장 수치
- `orders`: 주문 요청과 상태
- `fills`: 실제 체결 수량과 가격
- `trades`: 진입·청산 단위 손익
- `daily_summary`: 전체 일별 성과
- `strategy_daily_summary`: 전략별 일별 성과
- `strategy_universe_symbols`: 전략별 후보 구성

## 성과 판정

- 거래수와 평가기간을 항상 함께 표시한다.
- 승률만 보지 말고 순손익, 평균수익, 평균손실, profit factor를 함께 본다.
- 수수료·세금·슬리피지가 미반영이면 총손익이라고 명시한다.
- 특정 종목별 손익을 집계해 수익 편중을 확인한다.
- 전략 변경 전후 기간을 분리한다.
- 청산 사유별 손익을 집계해 손절, 부분익절, 본전청산, trailing 효과를 확인한다.

## 거래 없음 분류

- 후보 없음: snapshot 또는 universe가 0
- 후보 탈락: 전략 조건이나 장중 실행 필터 차단
- 주문 차단: 최대포지션, 일일손실, 주문수, 중복주문, 재진입 제한
- 주문 실패: 키움 반환값 또는 서버 메시지 오류
- 체결 실패: 미체결, 취소, timeout 또는 체결 이벤트 누락

## 주의할 왜곡

- 후보가 없던 날을 패배로 계산하지 않는다.
- 부분익절 후 손절이어도 최종 순손익이 양수면 거래 결과는 순손익 기준으로 본다.
- 서로 다른 전략 버전을 한 집계로 결론 내리지 않는다.
- 백테스트 결과와 모의투자 체결 결과를 합치지 않는다.
