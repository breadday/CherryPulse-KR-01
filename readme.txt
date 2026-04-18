실행 정리

1. 기본 권장 모드
- `.env`에서 `RUN_MODE=paper`
- 이 상태는 모의투자이며 실제 주문이 전송되지 않습니다.

2. 전날 종목 저장
- `python save_condition_snapshot.py`
- 결과: `condition_snapshot.json` 생성

3. 장중 실행
- `python main_live.py`
- 동작:
- snapshot 종목 로드
- 조건검색 `주도주_스나이퍼` 실시간 감시
- 모멘텀 / 주도주 눌림 / 종가매수 전략 검사
- 전략별 신호, 주문, 체결, 손익을 SQLite에 기록

4. 전략별 성과 확인
- `python analyze_strategy_performance.py --db C:\Users\YOUR_USER\AppData\Local\CherryPulse-KR-01\cherry_pulse.sqlite3 --date YYYY-MM-DD`

5. 실주문 전환
- `.env`에서 `RUN_MODE=live`
- 이 경우 실제 주문이 전송되므로 모의투자 검증 후에만 사용합니다.
