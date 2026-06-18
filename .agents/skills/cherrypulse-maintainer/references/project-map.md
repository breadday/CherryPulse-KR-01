# 프로젝트 구조

## 현재 운영 기준

- 기본 축은 일봉 후보 기반 스윙 매매다.
- `condition_snapshot.json`에 기록된 전략별 후보만 다음 거래일에 감시한다.
- `ENABLE_CONDITION_SEARCH = False`가 기본이며 조건검색과 틱 단타는 연구 대상으로 둔다.
- `RUN_MODE=live`와 키움 모의투자 계좌는 실주문 API 경로를 사용한다.
- 계좌가 실계좌로 바뀌면 실제 자금 주문이 발생할 수 있다.

## 파일 책임

- `main_live.py`: 시작, 장시간, 계좌 동기화, snapshot 로딩, 종료
- `config_live.py`: 실행모드, 전략 활성화, 주문금액, 리스크, timeout
- `build_daily_strategy_snapshot.py`: 일봉 CSV에서 전략별 후보 생성
- `download_daily_candles.py`: 키움 일봉 다운로드
- `universe_manager.py`: 후보를 전략별 universe로 분배
- `selectors/*`: snapshot 해석과 전략별 실행 필터
- `strategies/*`: 매수 신호 판단. 주문과 계좌조회 금지
- `engine.py`: 신호, 리스크, 주문, 체결, 포지션 감시 조정
- `core/portfolio.py`: 현금과 포지션 상태
- `core/order_manager.py`: 주문과 미체결 상태
- `core/risk_manager.py`: 주문 전 리스크
- `broker/kiwoom_broker.py`: 키움 로그인, TR, 실시간, 주문, 체결 이벤트
- `infra/sqlite_store.py`: SQLite 기록

## 데이터 흐름

1. `download_daily_candles.py`가 `data/daily/*.csv`를 갱신한다.
2. `build_daily_strategy_snapshot.py`가 `condition_snapshot.json`을 만든다.
3. `validate_daily_snapshot.py`가 최신 거래일과 휴장일을 검증한다.
4. `main_live.py`가 후보를 전략 universe에 등록한다.
5. 전략 신호가 발생하면 엔진이 리스크 검사 후 주문한다.
6. 주문·체결·거래 결과가 SQLite와 로그에 저장된다.

## 설계 경고

- 일봉 전략에 공통 단타 청산을 강제로 적용하지 않는다.
- 후보 종목을 모든 전략에 무차별 배포하지 않는다.
- `engine.py`가 전략 계산기 역할까지 맡지 않게 한다.
- `condition_snapshot.json`, 로그, DB는 런타임 산출물이며 비밀값을 포함하지 않게 한다.
