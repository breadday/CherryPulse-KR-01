---
name: cherrypulse-maintainer
description: CherryPulse-KR-01 키움 자동매매 프로젝트를 안전하게 진단, 수정, 검증하는 저장소 전용 스킬. 사용자가 매매 로그 분석, SQLite 성과 진단, 일봉 snapshot 오류, 키움 주문·체결·재접속 문제, 전략 추가·변경, 백테스트, 한글 인코딩, 실행 배치파일, Git 정리를 요청할 때 사용한다.
---

# CherryPulse 유지보수

## 시작 절차

1. 저장소 루트의 `AGENTS.md`와 그 문서가 지정한 `docs/harness/*.md`를 먼저 읽는다.
2. `git status --short --branch`로 기존 변경을 확인하고 사용자 변경을 되돌리지 않는다.
3. 요청을 후보선정, 전략판단, 리스크, 주문·체결, 운영, 분석 중 하나로 분류한다.
4. 파일 책임이 불분명하면 `references/project-map.md`를 읽는다.

## 안전 원칙

- `RUN_MODE=live`는 모의투자 계좌에서도 실제 주문 API를 호출한다. 사용자가 명시하지 않으면 `main_live.py`를 실행하지 않는다.
- 계좌가 실계좌일 가능성을 항상 고려한다. 주문 테스트를 위해 전략 조건이나 안전장치를 임의로 해제하지 않는다.
- `.env`, 계좌번호, 비밀번호, 텔레그램 토큰을 출력하거나 커밋하지 않는다.
- 조건검색과 틱 단타를 몰래 활성화하지 않는다.
- 보유종목은 전략 소유권과 청산 규칙을 확인한 뒤 다룬다.
- 거래 결과가 나쁘다는 이유만으로 당일 조건을 반복 조정하지 않는다. 전략 버전을 고정하고 표본을 누적한다.

## 요청별 작업

### 로그와 성과 분석

1. `scripts/diagnose-performance.ps1`을 실행해 최근 DB 요약과 snapshot 상태를 확인한다.
2. 실제 성과는 `%LOCALAPPDATA%/CherryPulse-KR-01/cherry_pulse.sqlite3`의 `trades`와 `strategy_daily_summary`를 우선한다.
3. 전략별 거래수, 승률, 순손익, 평균수익, 평균손실, profit factor, 최대 연속손실을 구분한다.
4. 전체 기간과 최근 변경 이후 기간을 섞지 않는다. 전략 버전 또는 변경일을 밝혀 비교한다.
5. 표본이 30건 미만이거나 특정 종목이 수익의 20% 이상이면 잠정 결과라고 명시한다.
6. 거래가 없으면 후보 없음, 진입차단, 주문차단, 체결실패를 분리해서 진단한다.

자세한 DB 기준은 `references/diagnostics.md`를 읽는다.

### 전략 추가 또는 변경

1. 전략 가설, 데이터 시점, 진입, 청산, 보유기간, 무효화 조건을 먼저 적는다.
2. 기존 전략을 덮어쓰지 말고 독립된 전략명과 설정으로 추가한다.
3. 일봉 후보 생성과 장중 실행 필터를 분리한다.
4. 전략마다 후보, 포지션 소유권, 청산, 성과를 독립 기록한다.
5. 과거 공시나 실적은 실제 발표일 이후에만 사용해 미래정보 누수를 막는다.
6. 비용, 세금, 슬리피지와 다음 거래일 체결 가능 가격을 백테스트에 반영한다.
7. 백테스트, 모의투자, 실전형 모의투자 순으로 승격한다.

전략 통과 기준과 실적 모멘텀 방향은 `references/strategy-governance.md`를 읽는다.

### snapshot과 일봉 데이터

- `condition_snapshot.json`은 직접 고치지 말고 생성 스크립트로 갱신한다.
- `latest_data_date`, 후보별 `last_date`, 휴장일, 가짜 단일가 봉과 거래량 0 데이터를 확인한다.
- 검증 실패를 무시하고 `main_live.py`를 우회 실행하지 않는다.
- 오래된 일봉이면 다운로드 원인을 먼저 해결한다.

### 주문·체결·재접속

- `broker/kiwoom_broker.py`는 키움 I/O, `engine.py`는 조정, `core/*`는 상태와 리스크 책임을 유지한다.
- 로그만 보고 체결을 추정하지 말고 `orders`, `fills`, `trades`, 계좌 동기화 결과를 함께 확인한다.
- 재접속 루프에는 제한, timeout, 알림 throttling이 있어야 한다.
- 프로세스 강제종료 전 미체결·보유종목 상태를 기록한다.

## 수정 규칙

- Python과 Markdown은 UTF-8로 유지한다.
- 배치파일은 CMD 호환 문법과 CRLF를 유지하고 한글 경로 quoting을 확인한다.
- `engine.py`에 새 전략 조건을 직접 누적하지 말고 `strategies/`와 `selectors/`로 분리한다.
- 설정값은 `config_live.py`에 두되 비밀값은 환경변수로만 받는다.
- 생성 데이터와 로그를 소스 코드 커밋에 무분별하게 포함하지 않는다.

## 검증 절차

수정 범위에 맞춰 최소한 다음을 실행한다.

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; files=['main_live.py','engine.py','broker/kiwoom_broker.py','config_live.py','build_daily_strategy_snapshot.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
.venv\Scripts\python.exe validate_daily_snapshot.py
```

- 전략 변경이면 해당 백테스트를 추가 실행한다.
- snapshot 검증이 데이터 노후로 실패하면 코드 성공으로 포장하지 않는다.
- `git diff --check`와 `git status`를 마지막에 확인한다.
- 사용자가 요청한 경우에만 커밋·push한다.

## 완료 보고

다음 네 가지를 한국어로 짧게 보고한다.

1. 발견한 원인
2. 변경한 내용
3. 실행한 검증과 결과
4. 남은 실거래 위험 또는 데이터 부족
