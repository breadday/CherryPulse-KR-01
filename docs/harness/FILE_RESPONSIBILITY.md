# 파일 책임표

AI와 사람이 같은 기준으로 작업하기 위한 파일 책임표다. 새 기능은 먼저 어느 책임에 속하는지 판단한 뒤 수정한다.

## 실행과 운영

- `main_live.py`: 프로그램 시작, 장 시간 판단, 계좌 동기화, 후보 로딩, 실시간 등록, 종료 흐름을 담당한다.
- `config_live.py`: 실행 모드, 전략 on/off, 주문 금액, 리스크 제한, 장 시간, timeout 설정을 담당한다.
- `run_main_live.bat`: 실전형 모의투자 실행용 배치파일이다.
- `run_build_daily_strategy_snapshot.bat`: 일봉 후보 생성용 배치파일이다.

## 일봉 후보 생성

- `build_daily_strategy_snapshot.py`: 일봉 CSV를 읽어 전략별 다음날 후보를 만들고 `condition_snapshot.json`에 저장한다.
- `download_daily_candles.py`: 키움에서 일봉 데이터를 내려받아 `data/daily`에 저장한다.
- `data/csv_loader.py`: CSV 일봉 데이터를 표준 `BarData`로 읽는다.
- `condition_snapshot.json`: 다음 실행에서 감시할 전략별 후보 목록이다. 수동으로 고치기보다 생성 스크립트로 갱신한다.

## 전략과 후보 분리

- `universe_manager.py`: snapshot 후보를 전략별 유니버스로 분배한다.
- `selectors/snapshot_selector.py`: snapshot 파일을 읽고 종목, 이름, 전략 태그를 해석한다.
- `selectors/*`: 장중 필터 또는 전략별 유니버스 필터 역할이다.
- `strategies/*`: 실제 매수 신호 판단을 담당한다. 주문 실행이나 계좌 조회를 직접 하면 안 된다.
- `strategies/composite_strategy.py`: 활성 전략들을 순서대로 실행하고 첫 신호를 반환한다.

## 주문, 보유, 청산

- `engine.py`: 신호 수신, 리스크 확인, 주문 제출, 체결 반영, 보유종목 감시, 청산 로직을 담당한다.
- `core/portfolio.py`: 현금과 보유 포지션 상태를 담당한다.
- `core/order_manager.py`: 주문 상태와 미체결 주문을 담당한다.
- `core/risk_manager.py`: 주문 전 리스크 판단을 담당한다.

## 외부 연결

- `broker/kiwoom_broker.py`: 키움 OpenAPI 연결, TR 조회, 실시간 등록, 주문/취소, 체결 이벤트를 담당한다.
- `infra/sqlite_store.py`: SQLite 기록 저장을 담당한다.
- `infra/telegram_notifier.py`: 텔레그램 알림을 담당한다.

## 검증과 분석

- `quant_bottom_reversal_backtest.py`: 바닥패턴 일봉 백테스트를 담당한다.
- `optimize_bottom_reversal_quant.py`: 바닥패턴 파라미터 최적화를 담당한다.
- `analyze_strategy_performance.py`: DB 기반 전략 성과 분석을 담당한다.
- `compare_four_strategies.py`: 전략 비교 분석을 담당한다.

## 수정 전 판단 기준

- 전략 조건을 바꾸면 `strategies/`, `build_daily_strategy_snapshot.py`, 백테스트 파일 중 어느 쪽인지 먼저 나눈다.
- 주문/체결/보유 문제는 `engine.py`, `core/*`, `broker/kiwoom_broker.py`를 먼저 확인한다.
- 후보 종목이 이상하면 `build_daily_strategy_snapshot.py`, `condition_snapshot.json`, `universe_manager.py`를 먼저 확인한다.
- 실행 시간/종료/조건검색 문제는 `main_live.py`, `config_live.py`를 먼저 확인한다.
