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
