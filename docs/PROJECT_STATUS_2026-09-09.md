# CherryPulse-KR-01 프로젝트 진행 현황

- 점검일: 2026-09-09
- 점검 기준 브랜치: main
- 현재 HEAD: dc1613ab80366ffbc77583e978a81b3d0dcf7e99
- 최근 커밋: 문서: CherryPulse 소스 분석 추가
- 최근 코드 변경 커밋: b65dec1bff718341c3fd8a2c9b5f2b1c93d010e8
- 저장소: https://github.com/breadday/CherryPulse-KR-01
- 점검 방법: GitHub 저장소 트리, 설정·실행 파일, 전략·브로커·백테스트 코드, 최근 커밋을 정적 확인
- 주의: 실제 키움 접속, 주문, SQLite 운영 데이터, 당일 로그는 확인하지 않았다. 따라서 실제 수익성과 실전 체결 안정성은 이 문서만으로 판단할 수 없다.

## 1. 현재 단계

현재 프로젝트는 **일봉 후보 기반 자동매매의 기능 구현과 모의투자형 실행 흐름이 구성된 단계**다.

다만 다음 단계인 실계좌 투입 준비가 끝난 상태는 아니다.

- 기능 구현 수준: 중후반
- 모의투자 검증 기반: 있음
- 자동화 회귀 테스트·CI: 부족
- 실계좌 안전성: 보완 필요
- 전략 수익성 검증: 운영 전략과 완전히 일치하지 않아 재검증 필요

### 한 줄 평가

> 일봉 후보 생성 → 전략별 후보 분리 → 장중 감시 → 리스크 검사 → 키움 주문·체결 → SQLite·텔레그램 기록까지 연결된 MVP다. 현재는 실계좌보다 모의투자와 전략 검증을 계속해야 하는 상태다.

## 2. 구현된 범위

| 영역 | 현재 상태 | 확인 근거 |
|---|---|---|
| 실행 구조 | 구현됨 | main_live.py, run_main_live.bat |
| 설정·환경변수 | 구현됨 | config_live.py, .env.example |
| 일봉 데이터 | 구현됨 | data/daily, download_daily_candles.py |
| 후보 생성 | 구현됨 | build_daily_strategy_snapshot.py |
| 전략별 유니버스 | 구현됨 | universe_manager.py, selectors/snapshot_selector.py |
| 활성 전략 | 3개 활성 | bottom_reversal, leader_pullback, close_buy |
| 비활성 전략 | 2개 비활성 | momentum, vcp_box |
| 키움 연결 | 구현됨 | broker/kiwoom_broker.py |
| 주문·체결 처리 | 구현됨 | engine.py, broker/kiwoom_broker.py |
| 리스크·보유 관리 | 구현됨 | engine.py, core/portfolio.py, core/risk_manager.py |
| SQLite 기록 | 구현됨 | infra/sqlite_store.py |
| 텔레그램 알림 | 구현됨 | infra/telegram_notifier.py |
| 백테스트 | 부분 구현 | backtest/*, quant_bottom_reversal_backtest.py |
| 운영 분석 | 구현됨 | analyze_strategy_performance.py, compare_four_strategies.py |
| AI 작업 하네스 | 구현됨 | docs/harness/*, AGENTS.md |
| 자동 테스트 | 부족 | 일반적인 tests/ 디렉터리 없음 |
| CI/CD | 없음 | .github/workflows 없음 |

## 3. 현재 운영 흐름

현재 기본 설계는 장중 단타가 아니라 **일봉 후보 기반 다음 거래일 스윙 매매**다.

1. data/daily의 종목별 일봉 CSV를 읽는다.
2. build_daily_strategy_snapshot.py가 전략별 후보를 만든다.
3. condition_snapshot.json에 후보와 전략 태그를 저장한다.
4. main_live.py가 snapshot의 후보만 장중 감시한다.
5. 전략별 selector와 strategy가 매수 신호를 만든다.
6. engine.py가 손실 한도, 보유 수, 중복 주문, 주문금액 등을 검사한다.
7. 키움 API로 주문하고 체결 이벤트를 반영한다.
8. SQLite와 텔레그램으로 신호·주문·체결·성과를 기록한다.

조건검색은 기본 비활성이다.

- ENABLE_CONDITION_SEARCH = False
- 전략 후보는 snapshot 중심
- 실시간 틱 단타는 기본 매매 축이 아님

## 4. 전략별 현재 상태

| 전략 | 활성 여부 | 후보 방식 | 현재 설정상 의미 |
|---|---:|---|---|
| bottom_reversal | 활성 | 일봉 snapshot | 바닥권 하락 후 회복 후보 |
| leader_pullback | 활성 | 일봉 snapshot | 일봉 눌림목 후보 |
| close_buy | 활성 | 일봉 snapshot | 종가 매수 후보 |
| momentum | 비활성 | snapshot·조건검색 미사용 | 기존 단기 모멘텀 연구용 |
| vcp_box | 비활성 | snapshot·조건검색 미사용 | VCP·다바스 박스 연구용 |

현재 data/daily에는 20개 종목의 일봉 CSV가 있으며, 종목군이 반도체·장비주에 집중되어 있다. 따라서 현재 전략 성과가 전략 자체의 효과인지 특정 업종 장세의 효과인지 분리하기 어렵다.

## 5. 이미 구성된 안전장치

다음 안전장치는 코드에 반영되어 있다.

- 기본 RUN_MODE는 paper
- snapshot 생성일·최근 데이터일 검증
- 오래된 snapshot이면 신규매수 후보를 비우는 fail-closed 처리
- 전략별 일일 주문 수·최대 보유 수 관리
- 일일 손실 한도와 연속손실 보호
- 급등 종목 신규매수 제한
- 손절 후 당일 재매수 제한
- 주문 간격과 키움 TR 요청 속도 제한
- TR·조건검색 대기 timeout 래퍼
- 미체결 매도 취소·재매도 흐름
- 주문·체결·거래·유니버스의 SQLite 기록
- 텔레그램 운영 알림
- 장 종료 후 자동 종료 흐름

## 6. 현재 확인된 핵심 문제

### P0 — 실계좌 전 반드시 해결

#### 6.1 .env가 Git에 추적되고 있음

저장소 트리에 .env가 존재한다. .gitignore에 제외 규칙이 있더라도 이미 추적된 파일에는 자동으로 적용되지 않는다.

조치 순서:

1. 계좌·텔레그램 관련 비밀값을 교체한다.
2. git rm --cached .env로 추적을 중단한다.
3. _backups의 ZIP 파일에 비밀값이 포함됐는지 확인한다.
4. 과거 커밋에 유효한 비밀값이 있었다면 Git 기록 정리를 검토한다.

#### 6.2 live 모드의 이중 잠금 부족

config_live.py에서 RUN_MODE=live이면 주문 허용 경로가 열린다. broker/kiwoom_broker.py는 ACCOUNT_NO가 없을 때 로그인 계좌 목록의 첫 계좌를 선택할 수 있다.

필요한 보완:

- live에서는 ACCOUNT_NO를 필수로 한다.
- 모의투자 서버와 실서버를 확인해 기대 환경과 다르면 시작을 차단한다.
- 별도 일회성 확인값 또는 계좌 allowlist를 요구한다.
- 시작 로그에 마스킹 계좌, 서버 구분, 주문 허용 여부를 남긴다.

### P1 — 전략·운영 신뢰성

#### 6.3 leader_pullback과 close_buy의 실제 진입 조건 우회

STRATEGY_CONFIG의 daily_candidate_mode가 True다.

이 모드에서는 다음 전략이 일봉 후보에 들어온 뒤 장중 가격 변화 범위만 확인하고 신호를 낼 수 있다.

- leader_pullback: 장중 눌림·지지·반등 확인이 우회됨
- close_buy: RSI2, 저점 회복, 고점 대비 눌림, 점수·거래량 검사가 우회됨

따라서 현재 결과를 순수한 “리더 눌림목” 또는 “RSI2 종가매수” 성과로 해석하면 안 된다.

필요한 보완:

- daily_candidate_mode를 전략별 설정으로 분리한다.
- 우회 모드는 별도 전략명·버전으로 기록한다.
- 실제 사용할 진입 규칙을 고정한 후 백테스트와 모의투자를 다시 시작한다.

#### 6.4 snapshot 날짜 검증 정책 점검 필요

main_live.py와 validate_daily_snapshot.py는 generated_at이 실행 당일이 아니면 실패시키는 정책을 사용한다.

전날 장 마감 후 정상적으로 만든 후보를 다음 거래일에 사용하는 운영 방식과 충돌할 수 있으므로, generated_at보다 latest_data_date와 거래일 캘린더를 중심으로 검증하는 것이 안전하다.

#### 6.5 로그인 timeout 미적용

TR과 조건검색에는 timeout 래퍼가 있으나, broker/kiwoom_broker.py의 로그인 대기는 QEventLoop.exec_()를 직접 호출한다.

로그인 이벤트가 오지 않으면 시작 또는 재접속 흐름이 무기한 대기할 수 있다.

### P2 — 검증·유지보수

#### 6.6 백테스트가 운영 전략과 완전히 같지 않음

backtest/runner.py는 MomentumIntradayStrategy 중심의 단순 실행기다.

quant_bottom_reversal_backtest.py는 바닥반전 일봉 전략을 별도로 검증하지만, 운영 엔진의 다음 요소를 완전히 재현하지 않는다.

- 부분익절
- 트레일링 스톱
- 장중 필터
- 주문 지연과 부분체결
- 호가단위·상하한가·거래정지
- 실제 운영 전략별 유니버스
- 전략별 주문 한도와 계좌 리스크

#### 6.7 검증 하네스가 전체 회귀 테스트는 아님

run_verify_harness.bat가 현재 수행하는 일은 다음과 같다.

1. 핵심 Python 파일 문법 컴파일
2. 일봉 snapshot 생성
3. 바닥반전 백테스트 실행

주문 중복, 부분체결, 로그인 실패, timeout, snapshot 경계일, paper 모드의 SendOrder 미호출 등을 자동 회귀 테스트하지 않는다.

#### 6.8 테스트·CI 부재

현재 저장소 트리에는 일반적인 tests/ 테스트 스위트와 GitHub Actions workflow가 없다.

자동매매 프로젝트에서는 다음 테스트를 우선 추가해야 한다.

- paper 모드에서 SendOrder 미호출
- live 계좌·서버 불일치 시 주문 차단
- 동일 체결 이벤트 중복 수신 방지
- 부분체결·취소·재매도 상태 전이
- 일일 손실·연속손실 보호
- snapshot 주말·휴장일 경계
- 전략별 유니버스 격리
- 로그인·TR timeout

#### 6.9 저장소 위생

다음 생성물이 저장소에 포함되어 있다.

- Python __pycache__ 및 .pyc
- 프로젝트 백업 ZIP
- 고정된 샘플·일봉 데이터
- 버전이 고정되지 않은 일부 Python 의존성

기능에는 직접 영향이 없지만 저장소 재현성과 유지보수성을 떨어뜨린다.

## 7. 권장 진행 순서

### 1단계 — 보안·주문 차단

- 비밀값 교체
- .env와 백업 내 비밀값 제거
- live 계좌번호 필수화
- 모의/실서버 확인
- live 주문 이중 잠금
- 로그인 timeout

### 2단계 — 전략 정의 확정

- daily_candidate_mode의 의미 결정
- 전략별 진입·청산·보유기간·무효화 조건 문서화
- 전략 버전명을 주문·체결·거래 기록에 저장
- 현재 운영 규칙에 맞는 백테스트 재구성

### 3단계 — 종목선정 보강

- 20개 고정 종목 목록을 거래대금 기반 유니버스로 확장
- 관리종목·거래정지·신규상장 등 제외 기준 추가
- 업종별 최대 보유 수 제한
- 날짜별 유니버스 보관

### 4단계 — 회귀 테스트·CI

- pytest 테스트 스위트 추가
- GitHub Actions에서 문법·테스트·snapshot 검증
- paper 모드 주문 차단 테스트
- 체결·재접속·timeout 상태 테스트

### 5단계 — 모의투자 표본 확보

- 전략별 최소 30회 거래 전에는 잠정 결과로만 판단
- 여러 종목과 여러 시장 국면으로 검증
- 승률보다 기대값, profit factor, 최대낙폭, 연속손실 확인
- 충분한 모의거래 후에만 실계좌 전환 검토

## 8. 결론

CherryPulse-KR-01은 단순 아이디어 단계는 지났다.

현재 확보된 것은 다음과 같다.

- 일봉 후보 생성 흐름
- 전략별 후보·유니버스 분리
- 키움 연동 실행 구조
- 주문·체결·보유·리스크 관리
- SQLite·텔레그램 운영 기록
- 백테스트와 전략 분석 도구
- AI 작업 하네스 문서

하지만 아직 확보되지 않은 것은 다음과 같다.

- 실계좌를 안전하게 차단·허용하는 이중 잠금
- 비밀값이 제거된 저장소
- 운영 전략과 일치하는 백테스트
- 충분한 모의거래 표본
- 자동 회귀 테스트와 CI
- 업종 편향을 줄인 시장 유니버스

따라서 현재 프로젝트의 정확한 위치는:

> **기능 구현 완료에 가까운 MVP이며, 전략 검증·보안 강화·자동 테스트를 진행해야 하는 모의투자 단계**

실계좌 전환은 P0/P1 항목을 해결하고, 전략별 모의거래 결과를 별도로 확인한 뒤 결정해야 한다.
