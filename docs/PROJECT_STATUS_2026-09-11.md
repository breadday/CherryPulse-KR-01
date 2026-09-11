# CherryPulse-KR-01 프로젝트 현황

- 점검일: 2026-09-11
- 기준 브랜치: `automation/opencode-herdr-pipeline`
- 운영 기준: 키움 모의투자 계좌, `RUN_MODE=paper`
- 문서 성격: 2026-09-09 정적 진단 이후 실제 실행·테스트 결과를 반영한 최신 현황

## 현재 결론

일봉 후보 snapshot 기반의 실전형 모의투자 실행 흐름은 정상 기동과 장 종료 후 안전 종료까지 확인됐다. 다만 거래 데이터가 아직 없어 수익성이나 체결 품질은 판단할 수 없으며, 실계좌 전환은 승인 대상이 아니다.

## 확인된 정상 상태

- `RUN_MODE=paper`
- `ALLOW_LIVE_ORDERS=False`
- `ENABLE_CONDITION_SEARCH=False`
- 외부 후보 source 비활성
- `daily_snapshot_only` 운영 모드
- 최신 snapshot 검증: `SNAPSHOT_OK`, 최신 일봉 `2026-09-10`
- Python 3.8 32-bit broker import: `KiwoomBroker`
- 전체 회귀 테스트: `111 passed, 18 skipped`
- 장 종료 후 실행: 계좌/TR 동기화를 생략하고 정상 종료
- SQLite 현재 누적 건수: `trades=0`, `orders=0`, `fills=0`, `strategy_daily_summary=0`

## 최근 반영 내용

1. Python 3.8에서 broker annotation import가 가능하도록 postponed annotations를 적용했다.
2. broker 이름과 서버 메시지의 키움 CP949 깨짐 보정 경로를 적용했다.
3. 장 종료 후 `pending orders`와 `deposit` TR 조회를 생략해 `-300` 오류를 제거했다.
4. Telegram 시작 로그에서 `chat_id`를 완전 마스킹했다.
5. `requests`를 실행 의존성에 명시했다.
6. snapshot·broker import·timeout·리스크·복구 회귀 테스트와 GitHub Actions 설정을 저장소에 반영했다.
7. 로그인 이벤트 대기에도 20초 timeout을 적용하고 실패 경로 회귀 테스트를 추가했다.

## 남은 작업

### 즉시 조치

- Telegram token 교체를 완료했고, `.env`와 기존 백업 ZIP은 로컬에 보존한 채 Git 인덱스에서 제거했다. 이후 백업도 `_backups/` 규칙으로 추적되지 않는다. 이 staged 삭제와 `.gitignore` 변경은 다음 커밋에 반영해야 한다.
- 과거 커밋에 비밀값이 남아 있는지는 별도 Git 이력 점검이 필요하다.
- `RUN_MODE=live` 전환 시 계좌번호 필수화, 모의/실서버 확인, 별도 승인값을 추가한다.

### 운영 검증

- 장중 모의투자에서 후보 감시, 매수 차단, 체결, 미체결, 재접속, 종료 로그를 누적한다.
- 거래가 발생한 뒤 `orders`, `fills`, `trades`, `strategy_daily_summary`를 함께 대조한다.
- 최소 20거래일 또는 충분한 실패 사례가 쌓이기 전에는 전략 성과를 결론 내리지 않는다.
- 전략별 최소 30거래 표본, 기대값, profit factor, 최대낙폭, 연속손실, 종목 집중도를 별도로 검토한다.

### 구조 개선

- 운영 전략과 동일한 규칙·비용·슬리피지를 사용하는 백테스트를 구축한다.
- 고정 20종목 중심의 일봉 수집을 거래대금·업종 분산 유니버스로 확장한다.
- `engine.py`의 리스크·청산·체결·저장 책임을 단계적으로 분리한다.

## 안전한 일일 실행 순서

```powershell
py -3.8-32 download_daily_candles.py
py -3.8-32 build_daily_strategy_snapshot.py --input data\daily --output condition_snapshot.json
py -3.8-32 validate_daily_snapshot.py
py -3.8-32 -B -m pytest -q
```

검증이 실패하면 snapshot을 우회해 `main_live.py`를 실행하지 않는다. `main_live.py`는 모의투자 계좌와 장중 운영 검증이 명시적으로 필요한 경우에만 실행한다.

## 참고 문서

- 과거 정적 진단: `docs/PROJECT_STATUS_2026-09-09.md`
- 소스 구조 진단: `docs/SOURCE_ANALYSIS.md`
- 작업별 증거: `docs/agent-handoff/`
- 운영 원칙: `docs/harness/`
