# 다음 작업 참고 메모

- 작성일: 2026-09-11
- 현재 브랜치: `automation/opencode-herdr-pipeline`
- 현재 운영 모드: 키움 모의투자, `RUN_MODE=paper`

## 현재 완료 상태

- `ALLOW_LIVE_ORDERS=False`
- `ENABLE_CONDITION_SEARCH=False`
- 일봉 snapshot 기반 후보 감시
- snapshot 검증 정상
- Python 3.8 32-bit broker import 정상
- 로그인 이벤트 timeout 적용
- 계좌번호 10자리 형식 검증
- 키움 모의투자/실서버 구분 검증
- 실서버 명시적 승인값 보호
- Telegram `chat_id` 로그 마스킹
- `.env`와 백업 ZIP Git 추적 해제
- 전체 회귀 테스트: `117 passed, 18 skipped`

## 장외에 할 일

```powershell
py -3.8-32 validate_daily_snapshot.py
git status --short
```

장외의 `main_live.py` 실행은 매매 검증이 아니라 자동 종료와 계좌/TR 조회 생략 확인용이다.

## 다음 거래일 장중 검증

```powershell
py -3.8-32 download_daily_candles.py
py -3.8-32 build_daily_strategy_snapshot.py --input data\daily --output condition_snapshot.json
py -3.8-32 validate_daily_snapshot.py
py -3.8-32 -B -m pytest -q
py -3.8-32 main_live.py
```

확인할 로그:

- `RUN_MODE=paper`
- `ALLOW_LIVE_ORDERS=False`
- 기대 서버와 실제 키움 서버 일치
- `daily_snapshot_only`
- 후보 실시간 등록
- 계좌·미체결 동기화
- 주문 차단 또는 paper 처리
- 종료 시 정상 정리

## Push 전 체크리스트

1. `git status --short`로 미커밋 파일을 확인한다.
2. 데이터·`.pyc`·OpenCode 설정 등 기존 작업물을 기능별로 분리한다.
3. 테스트 통과 결과와 관련 문서가 함께 있는지 확인한다.
4. `.env`, 계좌번호, 비밀번호, Telegram token이 staged diff에 없는지 확인한다.
5. `git diff --check`를 실행한다.
6. 커밋 후에만 현재 브랜치를 push한다.

현재 브랜치에는 안전 관련 커밋이 존재하지만, 아직 미커밋 작업물이 남아 있으므로 전체 변경사항을 검토하지 않은 상태에서 한꺼번에 push하지 않는다.

## 남은 개발 과제

- 장중 모의투자 운영 데이터 축적
- 실계좌 allowlist와 긴급 중지 스위치 검토
- 운영 전략과 일치하는 백테스트 보강
- 거래 데이터 발생 후 전략별 성과 분석
- 기존 미커밋 변경사항의 기능별 분리 및 정리
