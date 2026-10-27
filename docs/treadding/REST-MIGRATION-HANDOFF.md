# 다른 AI용 재개 지시서

대화 기억 없이 이 저장소에서 이어갈 수 있도록 작성했다. 최신 상태는 같은 폴더의
`REST-MIGRATION-STATUS.json`, 검증 결과는 `REST-MIGRATION-VERIFICATION.md`다.

## 시작

1. `git status --short`, `git branch --show-current`, `git log -5 --oneline` 확인.
2. 원격을 fetch하고 divergence를 확인한다. 사용자 변경은 보존한다.
   PR #3 병합 후 main에 이 기반이 있다면 최신 main에서 새 작업 브랜치를 만든다.
3. 루트 `AGENTS.md`, 전환 계획, 실행 계약·테스트 매트릭스·미확인 사항을 읽는다.
4. 상태 JSON에서 첫 미완료 작업을 선택하고 `in_progress`로 기록한다.
5. 관련 코드를 읽고 최소 단위부터 구현한다. 기존 가상 엔진과 실제 scope를 섞지 않는다.

## 다음 작업: R04 계속

R04 이력 TR 식별(`kt00007/kt00009/ka10076`, `POST /api/dostk/acnt`)은
`feature/rest-r04-history-spec`에 문서 경계로 기록했다. 전송 허용·원장 연결은
하지 않았고 `can_reconcile`은 false다. R02/R03 문서의 PC 검증 결과를 구분한다.
`execution.models.Scope`는 아직 virtual만 허용한다. 이 제한을 단순히 REST 문자열로 풀지 않는다.
다음은 모의계좌 실측(`probe_kiwoom_rest --execute-read-only --include-history`)으로
세 이력 TR의 실제 응답·페이지헤더를 확인하고, Q01/Q02/Q08 식별 근거를 확정한 뒤
REST 전용 scope를 설계한다.

## 다음 작업: R05 실증 실행

R05 실증 도구(`submit_paper_buy`, `verify_paper_linkage`)는 오프라인 검증했다.
[R05 기록](REST-R05-ORDER-DEMO.md) 순서대로 사용자 PC에서 미리보기·제출·연결
확인을 실행한다. 제출은 모의 1주 지정가 1회이며 자동 재시도·취소·원장 연결은 없다.

## R05 이후 차단 기록

R04 scope 게이트 이후는 실측 없이는 오프라인으로 진행하지 않는다.
R05 주문 dispatcher, R06 패턴·보호 연결, R07 무인 운영, R08 보드 인수는
모의계좌 실측(Q01/Q02/Q08 확정)과 허용된 주문 실증 뒤에 착수한다.
차단 사유와 재개 조건은 상태 JSON의 `external_pending`을 따른다.
현재 잔고/미체결 두 조회만으로 orders/fills 근거를 만들지 않는다.
Q01~Q11 REST 식별·수량 의미가 실제 근거로 확인되기 전 실제 dispatcher를 활성화하지 않는다.
주식체결 가격 수신은 주문체결 사실이 아니다. 거래일·세션을 수신시각에서 만들지 않는다.
가상 reconciliation을 실제 계좌 대조 완료로 재사용하지 않는다.

## 검사

개발 환경에 검사 도구가 없으면 기존 격리 개발 환경에
`python -m pip install pytest==9.1.1 ruff==0.16.7 basedpyright==1.40.2`로 준비한다.
실제 WebSocket 도구 의존성은 `tools/requirements-rest-probes.txt`로 별도 설치한다.

```powershell
python tools/verify_rest_migration.py
python -m pytest -q --basetemp=results/rest-full-pytest
python -m execution
python -m ruff check .
python -m ruff format --check .
python -m basedpyright
```

전체 원장 검사는 Windows가 필요하다. Linux에서 msvcrt 에러를 제거하려고 잠금을
가짜 처리하거나 검사 성공으로 바꾸지 않는다. Linux의 REST 검사만 필요하면:
`python -m pytest --confcutdir=tests/rest tests/rest -q`.
검증 도구의 결과 파일은 실행 산출물로 Git 제외; 결과 요약은 검증 Markdown에 기록한다.

## 단계 종료·중단 직전

변경 파일·명령·exit code·미검증·차단 이유·다음 정확한 행동을 기록한다.
JSON과 인계 문서를 갱신하고 `git diff --check` 후 작은 한글 커밋으로 push한다.
원격 CI 결과를 기록하고 완료 상태로 올린다. 기존 Ruff/type baseline 오류와 이번 오류를 구분한다.
작업 중단 시 진행 중 단계와 수정 파일을 기록한다. 검증되지 않은 코드를 완료로 올리지 않는다.

## 다음 AI에 붙여넣을 문장

CherryPulse-KR-01의 REST 전환 작업을 최신 main에서 이어서 진행해.
AGENTS.md와 docs/treadding/REST-MIGRATION-HANDOFF.md, STATUS.json을 읽고,
첫 미완료 단계부터 계획·구현·테스트·검증·기록·한글 커밋·push를 반복해.
주문 전송 OFF를 유지하고 실제 증권사 검증이 필요한 부분은 구체적인 명령과 판정 기준을 남겨.
토큰이 부족해지면 안정된 작은 단위를 push하고 다음 작업을 기록해.

## 2026-10-18 메인 보드 확인·개선

`web/board/`에 초안 화면은 있었으나 README가 미구현으로 잘못 안내했다.
`web/index.html` 진입점과 기존 보드의 설정 현황·내부 메뉴를 추가했다.
실행: `python -m http.server 8080 --bind 127.0.0.1 --directory web`,
접속: http://localhost:8080/ . 기존 초안은 동일 브라우저·호스트·포트에서 유지한다.
Node 화면 테스트 24개 통과. Python REST 재검사는 현재 환경에 pytest가 없어 미실행.
실제 브라우저 렌더링·배포 URL·모바일 실기기·REST 엔진 상태 연동은 미검증이다.
R08 전체 완료로 올리지 않는다. 다음은 PC 브라우저에서 등록·연결·보관과 모바일
레이아웃을 확인하고 R04/R05 실증 결과 확보 후 실제 상태 동기화를 진행한다.

## 2026-10-19 보드 화면 1차 재배치

기준 main d5e5fae의 로그 요약·매수 미리보기를 보존했다. 종목 등록 폼과
백업 도구를 접고 카드 중심 보드를 추가했다. 각 카드의 상세·설정은 오른쪽
비모달 패널로 열며 종목 수정·출처·메모·손절 패턴·보관을 제공한다.
패턴 저장 후 패널 유지, 닫기/Esc 초점 복귀를 구현했다.
실행 상태는 미조회로 명시하며 초안으로 감시·주문 상태를 생성하지 않는다.
저장 키·백업 스키마·매수 규칙은 유지한다.
검사: node --test web/board/*.test.js → 29 passed(보드 25 + 보조 4),
HTML 중첩·ID 중복 검사와 git diff --check 통과.
브라우저 렌더링·모바일 실기기·실제 계좌 연결은 미검증이다.
다음: PC에서 카드·패널·좁은 화면을 확인하고, 매수 패턴의 종목별 연결은
백업 스키마 호환성까지 별도 설계한다. 현재 매수 패턴은 독립 초안·미리보기다.
R04/R05 실증 차단과 R08 전체 미완료는 유지한다.

## 2026-10-19 패턴 연결・미리보기 완료

사용자가 정한 3단계 중 메인 보드 재배치·종목 상세 패널은 PR #11로 반영했다.
이번 단계는 종목별 매수 패턴 연결과 연결 조건 미리보기를 구현했다.
- 상세·설정에서 매수/손절 패턴을 독립 연결·해제한다. 카드는 이름·버전·조건을 표시한다.
- 가상 현재가, 선택적 가상 평균 매수가로 연결한 조건만 평가한다.
- 평균 매수가 없는 비율 손절은 평가 보류로 표시한다. 비활성·미연결·연결 오류를 구분한다.
- 미리보기는 저장·시세 조회·주문을 수행하지 않는다. 기존 전역 매수 미리보기·로그 요약을 유지한다.
- 저장 키·schemaVersion 1을 유지하고 종목의 선택 필드 buyPatternId를 추가한다.
  새 버전은 기존 v1 백업을 읽는다. 새 매수 연결을 포함한 백업은 구버전 화면에서
  지원하지 않는 필드로 거부되므로 복원 전 최신 코드를 사용한다.
- 백업은 존재하지 않는 ID와 매수/손절 종류가 뒤바뀐 연결을 거부한다.
검사: node --test web/board/*.test.js → 35 passed, git diff --check 통과.
CI 검증기가 보드·미리보기·로그 테스트를 모두 실행하도록 확장했다.
완료 범위: 요청한 3단계의 초안 UI 소프트웨어 구현. 브라우저 시각·모바일 실기기
인수는 미검증이다. 실제 시세·계좌·주문·엔진 연동과 R04/R05 실증은 별도 대기다.
PC 확인: 최신 main을 pull하고 http://localhost:8080/ 에서 강력 새로고침 →
매수/손절 패턴 작성 → 종목 상세에서 연결 → 가상 가격으로 미리보기 →
새로고침·전체 백업/복원 후 연결 유지 확인.


## 2026-10-19 원격 보드 소스 동기화 및 초안 안내

`git fetch origin` 후 origin/main의 PR #12 병합 커밋 `f4fde1d`를 확인했다. 로컬 보드 변경은 한글 커밋으로 보존하고 해당 main 위에 재배치했다. 종목 상세 drawer, 종목별 매수·손절 연결, 조건 미리보기는 원격 구현을 사용하며, 초안 모드 경고 바·등록/보관 건수·모바일 상태 탭만 추가했다. 주문 활성화와 엔진 연결은 없다.
검사: `node --test web/board/*.test.js` 35개 통과, 두 변경 JS 파일 `node --check` 통과, `git diff --check` 통과. REST 검증은 실행 호스트에 Python 3이 설치되지 않아 미실행이다. 화면 렌더링·모바일 실기기 확인은 대기 중이다. R04 상태 및 주문 OFF를 유지한다.
push 커밋 `3f30ba0`의 GitHub Actions run `39259426413` 성공. 로컬 Python 3 부재로 REST 오프라인 스크립트는 로컬 미실행이며 CI에서 검증했다.

## 2026-10-19 HERMES TASK 경로 수정 및 게이트 점검

`docs/HERMES-TASK-2026-10-19.md` TASK-1을 반영했다. `AGENTS.md`는 실제
`docs/treadding/` HANDOFF/STATUS 경로를 가리킨다. 사용자 제공 `check.py`는
네 루트 레거시 엔진 경로를 활성 필수 파일에서 분리하고, 보관본이 확인되면
DEPRECATED로 표시한다. 자체 back-import 검사 오탐도 제외했다.

검사: `py check.py` 필수 문서 6개·보관본 4개 확인, 미진행 및 활성 back import
경고 0건. `tests/test_check_script.py` 1 passed. 전체 Python 회귀 328 passed,
Node 보드·미리보기·로그 35 passed, `git diff --check` 통과.

`py -3.10-32 tools/verify_rest_migration.py` 실행에서 REST 테스트 145개,
Ruff/format, Node 35개, diff 검사는 통과했다. `basedpyright` 미설치로 타입 검사
항목이 실패해 verifier 전체 `passed:false`다. 이는 실제 계좌 검증이 아니다.
R04는 `LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`, R08은
`BOARD_DRAFT_LINK_PREVIEW_VERIFIED_ENGINE_ACCEPTANCE_PENDING`으로 유지한다.
`known_baseline`의 기존 Ruff 47 / basedpyright 108은 유지했다.

TASK-2의 모의계좌 조회·장중 WebSocket·1주 지정가 제출 및 주문 연결은 정규장
밖에서 실행하지 않았다. TASK-3은 `/boards`, `/items`, `/patterns` 서버 라우트와
CRUD 인증/요청/응답 계약이 저장소에 없어 구현 차단; 주문 실행 계약을 웹 API
계약으로 추정하지 않았다. TASK-4 물리 iOS/Android 6/6은 실기기 접근이 없어
pending 유지. 근거와 재개 조건은 `HERMES-TASK-2026-10-19-RESULT.md`에 기록했다.

## 2026-10-20 오프라인 검증 6/6 통과 — verifier 타입검사 진입점 수정

이전 세션의 `rest_offline_followup: PARTIAL_BASEDPYRIGHT_NOT_INSTALLED` 원인은
basedpyright 미설치가 아니라 호출 방식이었다. `python -m basedpyright`는
nodejs-wheel 의존성을 요구하고 32비트 엔진 Python(3.10.8 32bit)에서는 빌드가
실패한다. `docs/DEVELOPMENT-ENVIRONMENT.md`가 정한 진입점은
`node .tools/typecheck/basedpyright/index.js --pythonpath <엔진Python>`이며
`.tools/typecheck`에 basedpyright 1.40.1을 재설치한 뒤 이 경로로 실행하면
어댑터 9개 파일 기준 0 errors다.

`tools/verify_rest_migration.py`의 타입검사 명령을 이 환경에 맞게 수정했다:
`.tools/typecheck/basedpyright/index.js`가 있으면 node 진입점, 없으면(CI 등
pip 설치 환경) 기존 `-m basedpyright`로 폴백한다. 명령 목록을 모듈 레벨
`CHECKS`로 추출해 고정 검사 6종이 드러나고, 보고서 조립은 `build_report`로
분리했다. `CHERRYPULSE_ENGINE_PYTHON` 환경변수로 --pythonpath를 지정할 수 있다.

검사(TDD): `tests/rest/test_verify_runner.py` 신규 5종 — RED(구현 전 5 failed)
확인 후 GREEN. 전체 오프라인 verifier `python tools/verify_rest_migration.py`
**exit 0, 6/6 OK**(REST pytest 150, ruff check/format, basedpyright node 진입점,
Node 보드 35, git diff --check). 전체 회귀 `pytest -q` **333 passed**
(기존 328 + 신규 5). `results/rest-migration-verification.json` 갱신.

R04 실증 대기는 유지: 실제 계좌·주문·WebSocket은 호출하지 않았다. 다음 행동은
정규장 시간(09:00~15:20 KST)에 지정 PC에서 모의 조회·수신·1주 지정가 실증이다.

## 2026-10-21 실증·수락 체크리스트 준비

정규장 실증(R04/R05)과 보드 시각 수락을 사용자 PC에서 흩어진 문서를 다시
찾지 않고 실행하도록 두 체크리스트를 만들었다. 상태 변경·주문 전송은 없다.

- `docs/treadding/REST-R04-LIVE-PROBE-CHECKLIST-2026-10-21.md`: 사전 준비물,
  예열·R04 읽기 5건·R05 1주 지정가·WebSocket·이력 연결 확인 5단계 명령과
  exit code 판정, 상태 갱신 조건, 증거 기록 양식. 거절 코드 20 재제출,
  UNKNOWN 재시도 금지 등 장애 대응을 포함한다.
- `docs/D02-PC-BROWSER-ACCEPTANCE-CHECKLIST-2026-10-21.md`: 기존 6항목 회귀
  확인 + 카드·상세 패널·패턴 연결·미리보기·경고 바 등 현재 보드 13항목과
  D02 기록 양식.

`STATUS.json`에는 `checklists` 포인터와 장 중 실증 문구로 바꾼
`next_action`만 반영했다. 다음 행동은 정규장 중 체크리스트 실행 →
증거 문서 기록 → 증거와 일치하게 상태 갱신이다. R04
`LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`, R05 실증 대기,
`can_reconcile=false`, 주문 OFF는 유지한다.

검증 중 `verify_rest_migration.py`와 `tests/test_check_script.py`의
subprocess가 Windows 로케일(cp949)로 디코드해 보드 Node 테스트 출력이 유실되고,
`check.py`는 cp949 콘솔에서 ✅·한글 출력 시 UnicodeEncodeError로 종료됐다.
두 subprocess 호출을 `encoding="utf-8", errors="replace"`로 고정하고
`check.py`는 stdout을 UTF-8로 재구성했다.
검사: REST pytest 151 passed(신규 러너 UTF-8 테스트 포함), ruff check/format,
basedpyright 0 errors, 보드 Node 35 passed(explicit stdout 회복 확인),
전체 회귀 334 passed, `py check.py` 통과, verifier exit 0 6/6 OK,
`git diff --check` 통과. 실제 계좌·주문·WebSocket 호출은 없다.

CI 기록: 현행 main이던 0f26041은 GitHub Actions Windows 러너에서
`check.py`가 exit 1로 run `39509273141` failure였고 인계서에 미기록이었다.
7844f93의 UTF-8 고정으로 run `39605264706`가 offline-rest·windows-engine
전부 success로 복구했다. 러너 알림은 Node 20 deprecated 경고뿐이다.

## 2026-10-21 키움 키 환경변수 폴백과 실증 준비 상태

사용자가 키움 모의 키를 환경변수 `KIWOOM_APP_KEY`/`KIWOOM_APP_SECRET`에 등록했다.
도구는 이제 `CHERRYPULSE_PAPER_APP_KEY`/`SECRET` → `KIWOOM_APP_KEY`/`SECRET`
순으로 읽는다(`adapters/kiwoom_rest_auth.py`의 `paper_credentials_from_env`).
네 도구(probe_rest, probe_ws, submit_paper_buy, verify_paper_linkage)를 이
헬퍼로 교체했고 키 값을 묻거나 출력하지 않는다.

지정 PC 준비물 확인(22:10경): `py -3.10-32` 3.10.8 32bit, 네 환경변수 존재
(True만 확인), 예열 `py -3.10-32 -m tools.probe_kiwoom_rest` exit 0.
기존 센티널(paper-buy-1016~1021)은 당일 날짜만 막으므로 내일 제출을
막지 않는다. 미해결 준비물: HTS(영웅문) 접속, 정규장 시간.

검증·검사: `verify_rest_migration.py`의 cp949 콘솔 출력 오류
(\u2714 유실)를 check.py와 같이 stdout UTF-8 reconfigure로 고정했다.
verifier 6/6 exit 0, REST pytest 153, 전체 회귀 336 passed(신규 폴백 2종 포함),
`git diff --check` 통과. 실제 계좌·주문·WebSocket 호출은 없다.
R04 `LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`, R05 실증 대기, 주문 OFF 유지.

## 2026-10-21 무인 R04/R05 실행 스크립트 (사용자 승인: 방식 A)

사용자 출근으로 지정 PC에서 직접 실행이 불가해 명시적으로 방식 A를 선택했다:
정규장 중 예약 작업으로 전 5단계 자동 실행. 구현:

- `tools/r045_morning_run.py`: 09:00~15:20 KST 게이트(주말·장 밖은 SKIP) →
  예열 → 읽기 5건(실패 시 즉시 중단, 주문 없음) → WS 30초 시세 캡처
  (`--quote-out` 파일 저장, 신선하지 않으면 중단) → 가격 상한 100000 초과 시
  주문 생략(PARTIAL_PRICE_OVER_CAP) → 1주 지정가 preview+confirm-execute 1회
  (재시도·취소 없음) → 30초 대기 → 사후 읽기 5건 → linkage 확인.
  증가(manifest)는 `results/r045-<날짜>/manifest.json`.
- WS 캡처에 `quote_sink` 콜백 추가(`adapters/kiwoom_rest_ws.py`),
  `probe_kiwoom_ws --quote-out <path>`에 마지막 시세 기록(가격·시각만).
- 검사: REST pytest 160, verifier 6/6 exit 0. 실제 호출은 아직 없다.
- 예약 작업 `CherryPulse-R045-Demo`: 평일 09:30,
  `scripts/r045-morning-run.cmd`.
- 운영자(저녁 세션)의 잔여 일: manifest·증가 검토 → 체크리스트 6절 양식으로
  증거 문서 기록 → 상태 JSON 갱신. 무인 상태 갱신은 하지 않는다.
  미체결 주문은 HTS에서 직접 확인·취소한다(자동 취소 도구 없음).

## 2026-10-21 docs 정리 (중복 삭제, 증거 보관)

참조가 전혀 없고 HANDOFF 동일 섹션과 중복인 3개를 삭제했다:
`docs/treadding/MAIN-BOARD-2026-10-18.md`,
`docs/treadding/BOARD-PATTERN-PREVIEW-2026-10-19.md`,
`docs/PROJECT-PROGRESS-AND-GAPS-2026-10-18.md`.
2026-09-25 키움 로컬 실측 증거 기록은 참조 0건이라
`docs/archive/KIWOOM-LOCAL-VERIFICATION-RESULT-2026-09-25.md`로 이동 보관했다.
이동한 문서의 상대 링크는 archive 내부에서 `../` 경계가 필요하나
해당 문서는 근거 스냅샷으로 중요 링크가 없어 갱신 없이 보관한다.
나머지 docs는 전부 상호 참조와 check.py 필수 경계라 정리하지 않았다.

## 2026-10-22 예약 실행 후속 — 개발 재개 지점

- 저장소 상태 확인: `main` HEAD `4678173`, origin/main과 일치. 사용자 미추적 파일 `CherryPulse-lite.zip`, `docs/사용법.md`는 보존.
- 예약 실행 manifest: PREWARM 0, READ_BEFORE 0, QUOTE_WS 1, ABORTED. 주문 단계 진입 없음.
- 기존 runner는 stdout/stderr 바이트 수만 남겨 WS JSON 요약을 버렸다. 구체 실패 원인은 이 실행에서 복구 불가.
- R045 runner는 후속 실행의 JSON 진단 중 안전한 allowlist 값만 manifest에 기록하도록 변경. stderr와 임의 필드는 보관하지 않는다. 회귀 테스트는 안전 필터 및 WS 실패 시 무주문 중단을 검증한다.
- 오프라인 검증 현황 및 최신 커밋은 이 handoff 아래의 task 결과 문서와 STATUS를 함께 확인한다. 실제 WS/계좌/주문 증거가 생기기 전 R04/R05를 승격하지 않는다.
- TASK-3은 보드 CRUD 서버 API 계약(호스트·인증·요청/응답·버전 충돌)이 제공되지 않아 미구현. 임의 API를 만들지 않는다. TASK-4 실기기 iOS/Android 6/6 및 클라우드 인증/동기화는 사용자 장치·환경이 필요하다.
- 예약 작업 `CherryPulse-R045-Demo`는 평일 09:30 활성, 다음 실행 2026-10-23 09:30. 스케줄러 변경 없음. 성공할 경우 기존 사용자 승인 runner는 모의 1주 지정가를 1회 시도하므로 실행 후 manifest/HTS 미체결을 감독 검토한다.

## 2026-10-22 보드 API·외부 인계 자료 구체화

사용자 요청 4항목을 `docs/api/BOARD-API-HANDOFF.md`로 모았다.
- 현행 저장소에 실제 CRUD 서버·API 호스트·인증 설정이 없음 확인.
- `docs/api/board-api.openapi.draft.json`: 검토용 OpenAPI 0.1.0-draft 제안.
  실제 계약을 받았다는 의미가 아니며 `.invalid` URL과 미배포 표시를 사용한다.
- `board-api.fixtures.json`: 합성 예시 10개와 서버 인수 시나리오. 실행 중 mock 서버는 아님.
- `board-api.environment.template.json`: 서버 URL·인증·클라우드/소유/보존 미정값을 null로 기록.
- 모바일 체크리스트의 과거 SHA·매수 연결 없음 문구를 현행 6항목으로 교정.
  iOS/Android는 NOT_RUN 유지. 휴대폰 localhost와 PC 주소 차이·Origin별 초안 저장을 안내.
검증: OpenAPI 3.0.3 PASS, 합성 예시 스키마10/10 PASS, Node35 passed,
git diff --check PASS. 업무/서버 인증/실기기 인수를 통과한 것은 아니다.
다음: 담당자가 계약 채택/수정·실제 서버 정보와 클라우드 결정표를 회신 →
확정 계약 기준으로 mock HTTP·서버/클라이언트를 구현한다. 계약 제안을
기존 실제 API로 간주하여 현재 보드 fetch나 내부 inbox를 인터넷에 노출하지 않는다.
R04/R05 증거와 사용자 지정 PC·모바일 접근은 이번에 확보하지 못했다.
기존 R04/R05 상태·예약 작업·주문 정책은 변경하지 않았다.

## 2026-10-25 사용자 제공 Cloudflare·Supabase 주소와 연결 준비

Cloudflare workers.dev 보드와 Supabase 프로젝트 URL은
`docs/api/CLOUD-CONNECTION-2026-10-25.md`에 기록했다.
현재 연결된 Supabase 앱으로 대상 프로젝트 get_project가 권한 오류로 실패했다.
DB·키·인증 설정은 미확인. 다른 프로젝트를 대신 사용하지 않았다.
Workers 정적 자산 + 설정 확인 API/보드 버튼을 추가했다. Node43 passed.
설정 API는 구성 상태만 표시하며 인증/CRUD/엔진 capability는 false다.
Wrangler 실제 배포·Supabase DB 변경·계좌/주문 실행은 하지 않았다.
다음 선행 조건: 대상 ref에 접근할 수 있는 Supabase 계정/조직 연결.
연결 후 실제 스키마와 RLS를 확인하고 로그인·CRUD를 구현한다.


## 2026-10-26 보드 클라우드 저장

Supabase board_snapshot_storage 마이그레이션을 적용했다. 비공개 스키마의
사용자별 스냅샷·저장 영수증, 소유자 RLS, invoker RPC를 사용한다. DB 실제
12 assertions와 security advisor(0 lints) 확인. 테스트 데이터는 rollback했다.
보드 이메일/비밀번호 로그인, 명시적 저장·불러오기, 교체 확인, 기대 버전과
동일 UUID 저장 재시도를 구현했다. 토큰은 메모리만 사용한다.
관련 문서: docs/api/CLOUD-BOARD-STORAGE-2026-10-26.md.
운영 Worker API 조회는 404. Cloudflare 배포 인증이 없어 운영 배포·실제 이메일
로그인·물리 모바일 검증은 미완료다. 소스 병합과 운영 배포를 구별한다.
R04/R05·주문 OFF·엔진 미연결은 유지한다.

2026-10-26: PR #17 코드 커밋 `682963e`의 GitHub Actions run `40323467969`에서
REST 오프라인 검사(Worker 빌드 포함)와 Windows 전체 회귀·가상 실행 모두 성공했다.
운영 Cloudflare 배포·실사용자 로그인 검증은 여전히 대기다.


## 2026-10-26 개인용 PIN·종목명 검색 (최신 사용자 결정)

사용자 요청으로 이메일 가입/인증 UI를 제거하고 4자리 숫자 비밀번호만
입력하는 개인용 접속으로 바꿨다. PIN 해시·세션 해시·영속 실패 잠금은
Supabase 비공개 스키마에서 관리한다. 공개 RPC는 invoker이고, 실제 권한
검사는 비공개 구현에서 PIN/세션을 확인한 뒤 수행한다. 실제 PIN을 Git에
남기지 않는다. 기존 사용자 초안은 유지한다.
공식 마스터 3,488개 종목의 이름→코드 자동 입력·유사명 선택도 추가했다.
Node 62개·Python REST 166개·PIN DB assertion 13개 통과, Worker 빌드 성공.
상세: docs/api/BOARD-PIN-AND-SYMBOL-SEARCH-2026-10-26.md.
Cloudflare 배포 인증은 사용자 PC에만 있으므로 최신 main 재배포 및
실제 PIN 화면·검색·모바일 인수는 아직 필요하다. R04/R05는 유지한다.


## 2026-10-26 운영 검색 타이머 오류 수정

사용자 Chrome에서 검색 입력·버튼의 Illegal invocation을 확인했다. 종목
파일과 JS 배포는 정상이었다. Window 타이머를 일반 객체 수신자로 호출한
기본 어댑터를 globalThis 래퍼로 고쳤다. 기본 어댑터·한글 조합·버튼·reset
회귀 검사 추가, Node 63개·Worker 빌드 통과. 등록 종목 필터와 새 종목
검색의 명칭도 구분했다. PIN은 변경하지 않았다. 최신 main 재배포 후
실제 브라우저 검색 성공 확인이 남았다.

## 2026-10-27 운영 검색 수정 확인 및 R045 실행 상태

운영 주소 `/board/`는 HTTP 200으로 열리고 HTML의 JS/CSS 버전이
`20261026-search-timer-fix`다. `/api/cloud-config`는 구성 준비 상태와
인증·보드 CRUD capability를 반환했다(엔진 capability는 false). 응답에 포함된
공개 publishable key 값은 기록하지 않았다.

사용자 Chrome의 운영 탭에서 PIN 화면은 표시됐고, 로그인 제출은 하지 않았다.
종목 등록에서 `삼성전자` 검색 후 005930이 자동 입력되었으며, 검색 목록에서
`삼성전자우`를 선택하자 이름과 코드가 005935로 바뀌었다. 입력 필드는 확인 뒤
비웠다. 실제 PIN 인증·서버 저장 왕복·모바일 인수는 미검증이다.

`results/r045-20261027/manifest.json` 확인: PREWARM과 READ_BEFORE는 exit 0,
QUOTE_WS는 CONNECT 단계 `DEPENDENCY_ERROR`, 연결 0·시세 0으로 중단했다.
주문 단계에는 진입하지 않았고 주문 OFF 및 `account_reconciled=false`다.
현재 작업 호스트에서는 `py -3.10-32`가 설치된 런타임을 찾지 못해 예약 실행과
같은 환경의 websockets 설치 여부를 확인할 수 없었다. 다음: 지정 PC에서 예약
작업의 Python 3.10-32 경로와 `websockets==15.0.1` 설치 여부, 안전한 허용 진단
결과를 확인한 뒤 의존성을 복구하고 다음 정규장 manifest를 검토한다. 주문 OFF와
R04 미승격은 유지한다.

로컬 Git 확인: `main` HEAD `7d7b000`이 `origin/main`과 일치. 기존 미추적
`CherryPulse-lite.zip`, `docs/사용법.md`는 보존했다. `git diff --check`는 기록
수정 전 통과했다.