# 변경 체크리스트

코드를 수정한 뒤 반드시 확인할 항목이다.

## 1. 설계 일관성

- 변경이 일봉 후보 기반 스윙 매매 원칙을 깨지 않는가?
- 장중 조건검색이나 틱 단타가 의도치 않게 다시 활성화되지 않았는가?
- 전략별 후보, 진입, 청산, 성과가 분리되어 있는가?
- 기존 보유종목 감시와 청산 로직에 악영향이 없는가?

## 2. 실전형 모의투자 안전성

- `RUN_MODE=live`일 때 실제 주문 경로가 호출될 수 있음을 고려했는가?
- 계좌가 모의투자인지 실행 전 확인 가능한가?
- 중복매수, 과열매수, 당일 손실, 최대 보유수 제한이 유지되는가?
- API 대기에는 timeout이 있는가?
- 장 종료 후 실행 시 즉시 종료되는가?

## 3. 전략 검증

- 일봉 후보 생성이 정상 동작하는가?
- 후보 파일에 전략 태그가 포함되는가?
- 백테스트 또는 과거 데이터 검증 결과가 있는가?
- 기대값, 거래수, 손익비를 확인했는가?
- 한두 종목에만 의존한 결과는 아닌가?

## 4. 로그와 DB

- 후보 생성 로그가 이해 가능한가?
- 매수 차단 사유가 로그에 남는가?
- 전략명, selector명, universe명이 DB에 기록되는가?
- 보유종목 수가 계좌 동기화 후 `health_check`에 반영되는가?

## 5. 인코딩

- 새 파일은 UTF-8로 저장했는가?
- 배치파일은 Windows CMD 호환을 위해 ASCII/CRLF로 저장했는가?
- 한글이 깨진 파일을 새로 만들지 않았는가?

## 6. 기본 검증 명령

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; [compile(Path(p).read_text(encoding='utf-8-sig'), p, 'exec') for p in ['main_live.py','engine.py','broker/kiwoom_broker.py','config_live.py','build_daily_strategy_snapshot.py']]; print('syntax ok')"
.venv\Scripts\python.exe build_daily_strategy_snapshot.py --input data\daily --output condition_snapshot.json
.venv\Scripts\python.exe quant_bottom_reversal_backtest.py --input data\daily
```

## 7. 완료 기준

- 문법 검사가 통과한다.
- 일봉 후보 snapshot이 생성된다.
- 전략별 후보 수가 출력된다.
- 장 종료 후 `main_live.py` 실행 시 주문 없이 즉시 종료된다.
- 장중 실행 시 `daily_snapshot_only` 모드로 시작한다.
