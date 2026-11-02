# REST 전환 첫 검증 — 2026-10-14

> 환경 구분: 아래 과거 Windows 검증 일부는 Python 3.10.8 32비트로 수행했지만,
> 이는 당시 사용 환경 기록이다. REST/HTTP/WebSocket의 아키텍처 요건은 아니다.
> 현재 REST 프로브 안내는 `py -3.10`을 사용하며 32/64비트 모두 가능하다.

기준 main `1ec7966`, Linux Python 3.12.14, pytest 9.1.1, Pydantic 2.13.5,
Ruff 0.17.0, basedpyright 1.40.2, Node 24.19.0.
기존 Windows/Python3.10 의존성 파일은 변경하지 않았다. 이 환경 검사가 Windows 인증은 아니다.

## 구현

- `adapters/kiwoom_rest_readonly.py`: 잔고 kt00018·미체결 ka10075만 허용,
  필수 입력·행·return_code·페이지 헤더 검증, 커서 반복/페이지 제한/예외에 불완전 표시.
- `adapters/kiwoom_rest_transport.py`: 고정 모의 호스트·계좌 조회 URL만 사용,
  외부 토큰 공급자·timeout·리디렉션 거절·자동 재시도 없음. 토큰 발급·속도제어는 미구현.
- `tests/rest/test_readonly.py`: synthetic 응답 검사. 계좌 배정·체결 반영·주문 기능 없음.
- `tools/verify_rest_migration.py`: 고정 오프라인 검사와 원자적 JSON 보고서.
- `.github/workflows/rest-migration.yml`: 오프라인 검사·Windows 전체 회귀와 데모.

## 실행 결과

| 검사 | 결과 |
|---|---|
| `python -m pytest --confcutdir=tests/rest tests/rest -q` | 28 passed |
| `node --test web/board/board.test.js` | 23 passed |
| 신규 4파일 Ruff check/format | 통과 |
| `git diff --check` | 통과 |
| `python -m pytest -q` 전체 | 수집 차단: 기존 Windows 전용 msvcrt, Linux에서 미검증 |
| 기존 전체 Ruff | 변경 전 47 errors, 이번 범위에서 미수정 |
| 기존 basedpyright | 변경 전 108 errors, 이번 범위에서 미수정 |

신규 검증기는 실패 시 비정상 종료하며 skipped 전체 엔진 검사를 성공으로 표시하지 않는다.
모의 transport 검사는 opener를 주입한 오프라인 검사다. 개발 중 monkeypatch 위치 오류로
synthetic token을 사용한 모의 서버 요청 1회가 시도되었다. 유효 키·계좌 정보는 사용하지 않았고
TRANSPORT_UNCONFIRMED로 종료했다. 위치를 수정한 최종 검사는 실제 네트워크를 호출하지 않는다.
증권사 인증·실시세·잔고·체결·주문 확인 근거 없음. 운영 DB/Windows 예약/배포 변경 없음.

## 미완료와 재개

R02부터 인계 문서 순서대로 진행한다. R01 모의 연결은 실제 사용을 위한 완성형 실행기가 아니다.
Windows CI의 실제 결과·원격 SHA·병합 상태는 아래 후속 기록에 추가한다.

## 원격 후속 검증

- PR: https://github.com/breadday/CherryPulse-KR-01/pull/3
- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38510395015
- Windows Python 3.10 x64: **210 passed**, 가상 데모 통과. 사용자 PC·32비트 OCX 검증은 아님.
- Linux Python 3.10: REST 28개·보드 23개·신규 파일 Ruff 0.16.7·format·diff 통과.
- 최초 Windows CI는 results 부모 경로 미생성으로 81 passed/129 errors.
  workflow에 폴더 생성을 추가한 후 위 결과로 해결했다. 실패 기록도 보존한다.
- 위 CI는 구현+workflow 수정 커밋 기준. 이 후속 기록은 증권사 계좌 검증을 추가하지 않는다.
- 인증·속도제어·WebSocket·실제 주문 연결 미구현은 상태 JSON에 유지한다.

## R02/R03 및 R04 준비 후속 검증

기준 main623f09f, feature/rest-auth-stream.
R02 모의 인증·갱신·pacing·읽기 도구, R03 모의 WebSocket 관측·재접속·신선도,
R04 조회 interval/revision 범위 경계를 구현했다.

- 로컬 REST/WS 113 passed, 보드23, 신규 production6파일 basedpyright0, Ruff/format 통과.
- R02 CI https://github.com/breadday/CherryPulse-KR-01/actions/runs/38513088606
- R03 CI https://github.com/breadday/CherryPulse-KR-01/actions/runs/38513857671
- R03 Windows Python3.10 전체284 및 가상 데모 통과. R04 후속 전체 검사는 PR #4 CI에서 확인한다.
- https://github.com/breadday/CherryPulse-KR-01/pull/4
- 테스트는 socket 연결을 차단했다. 유효한 키/토큰·계좌 없이 synthetic 응답만 사용했다.
- REST/WS 도구 기본 실행 network=false를 실제 확인했다. websockets15.0.1 설치 및
  사용 connect 옵션의 실제 라이브러리 signature 존재를 확인했다.
- 실제 로그인·계좌조회·시세·주문·운영 DB·사용자 PC 예약 변경은 수행하지 않았다.
- 실제 계좌/세션·주문/체결 mapping·원장 연결·무인 운영은 미완료다.

최종 로컬 회귀: REST/WS 115 passed. 인증 실패 뒤 두 번째 조회 호출 0,
비정상 payload 요약 실패 처리 검사를 추가했다. 새 production 타입0·보드23·Ruff/format 통과.
최종 Windows 전체 회귀 결과는 PR #4의 최신 head CI가 기준이다.

최종 원격 검증: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38514375059
Windows Python3.10 x64 전체 **297 passed**, 가상 데모 통과.
Linux REST/WS115·보드23·production6파일 타입0·신규 Ruff/format 통과.
이 결과는 R02/R03 소프트웨어와 R04 근거 경계 준비를 검증하며 실제 계좌/PC 인수가 아니다.

## R04 이력 식별 후속 검증 — 2026-10-14, `feature/rest-r04-history-spec`

로컬 Windows Python 3.10.8 32-bit, pytest 9.1.1, Ruff 0.16.7, Node 보드 검사.

- `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q`: **121 passed** (기존 115 + 신규 6).
- `ruff check` 신규 2파일 + 전체 REST 경계: 통과. `ruff format --check`: 통과.
- `node --test web/board/board.test.js`: 23 passed.
- `git diff --check`: 통과.
- `tools/verify_rest_migration.py`: basedpyright 미설치(`No module named basedpyright`,
  pip 설치 시 `nodejs-wheel-binaries` 빌드 실패)로 해당 1건만 실패, 나머지 5건 통과.
  신규 production 파일 타입 검사는 원격 CI에서 확인한다.
- 실제 로그인·계좌조회·시세·주문·운영 DB 변경 없음. `orders_enabled=false` 유지.

## R04 이력 식별 원격 CI — 2026-10-14, PR #5 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38537633401 (head `b2c3c38`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/5 (squash 병합, main `664daac`)
- Windows 전체 회귀 **303 passed**(기존 297 + 신규 6), 가상 데모 통과.
- 오프라인 REST 121·보드 23·Ruff/format·production 타입 0 errors·verifier `passed:true`.
- 로컬 basedpyright 미설치는 원격 타입 검사 0 errors로 해소했다.
- 실제 계좌·장중 수신·주문 실증은 여전히 미완료다.

## R04 이력 읽기 경계 로컬 검증 — 2026-10-14, `feature/rest-r04-history-reads`

로컬 Windows Python 3.10.8 32-bit, pytest 9.1.1, Ruff 0.16.7, Node 보드 검사.

- `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q`: **125 passed** (기존 121 + 신규 4).
- `ruff check` 전체 REST 경계·프로브·테스트: 통과. `ruff format --check`: 통과.
- `node --test web/board/board.test.js`: 23 passed.
- `git diff --check`: 통과.
- basedpyright 로컬 미설치로 미검증, 원격 CI에서 확인한다.
- 실제 로그인·계좌조회·주문·운영 DB 변경 없음. `orders_enabled=false` 유지.

## R04 이력 읽기 경계 원격 CI — 2026-10-14, PR #6 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38538467613 (head `8f31959`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/6 (squash 병합, main `7a3cfbc`)
- Windows 전체 회귀 **307 passed**(기존 303 + 신규 4), 가상 데모 통과.
- 오프라인 REST 125·보드 23·Ruff/format·production 타입 0 errors·verifier 통과.
- 모의계좌 실측·Q01/Q02/Q08 식별 확정·REST scope 설계는 여전히 미완료다.

## R04 scope 게이트 로컬 검증 — 2026-10-14, `feature/rest-r04-scope-gates`

로컬 Windows Python 3.10.8 32-bit, pytest 9.1.1, Ruff 0.16.7, Node 보드 검사.

- `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q`: **133 passed** (기존 125 + 신규 8).
- `ruff check` 검증 범위·`ruff format --check`: 통과.
- `node --test web/board/board.test.js`: 23 passed.
- `git diff --check`: 통과.
- basedpyright 로컬 미설치로 미검증, 원격 CI에서 확인한다.
- `execution.models.Scope` 변경 없음. 실제 로그인·계좌조회·주문·운영 DB 변경 없음.

## R04 scope 게이트 원격 CI — 2026-10-14, PR #7 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38539745699 (head `91a36c1`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/7 (squash 병합, main `69206cc`)
- Windows 전체 회귀 **315 passed**(기존 307 + 신규 8), 가상 데모 통과.
- 오프라인 REST 133·보드 23·Ruff/format·production 타입 0 errors·verifier 통과.
- R05 이후는 모의계좌 실측·허용된 주문 실증 뒤에 착수한다.

## R04 모의계좌 실측 — 2026-10-14, 사용자 PC

- 명령: `probe_kiwoom_rest --execute-read-only --max-pages 3 --include-history`, 3회 실행.
- 결과: exit 0, 5건 모두 `complete:true`·1페이지·`observed_rows:0`. 빈 모의계좌 확인.
- 확정: 연결·입력 승인·행 테이블·페이지 완전성. 미확정: Q01/Q02/Q08 식별 의미.
- 키·토큰·계좌번호·원문은 수신·저장하지 않았다. 주문 호출 없음.

## R05 실증 도구 로컬 검증 — 2026-10-14, `feature/rest-r05-order-demo`

로컬 Windows Python 3.10.8 32-bit, pytest 9.1.1, Ruff 0.16.7, Node 보드 검사.

- `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q`: **145 passed** (기존 133 + 신규 12).
- `ruff check` 검증 범위·`ruff format --check`: 통과.
- `node --test web/board/board.test.js`: 23 passed.
- `git diff --check`: 통과.
- basedpyright 로컬 미설치로 미검증, 원격 CI에서 확인한다.
- 주문 전송은 실행하지 않았다. 사용자 PC 실증 전이다.

## R05 거절 메시지 표시 로컬 검증 — 2026-10-14, `feature/rest-r05-order-message`

모의 제출이 `API_SUCCESS_UNCONFIRMED`로 거절됐으나 사유 메시지를 보고하지 않아
원인 구분이 불가했다. 보고서에 브로커 코드와 숫자 마스킹 메시지를 추가했다.

- `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q`: **145 passed**.
- `ruff check` 검증 범위·`ruff format --check`: 통과.
- `node --test web/board/board.test.js`: 23 passed.
- `git diff --check`: 통과.
- basedpyright 로컬 미설치로 미검증, 원격 CI에서 확인한다.

## R05 실증 도구 원격 CI — 2026-10-14, PR #8 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38548771036 (head `7c15f40`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/8 (squash 병합, main `cd0d0a8`)
- 초회 CI는 basedpyright 엄격 `reportUnknown*` 5건으로 실패했고 타입 캐스트 수정 후 재성공했다.
  실패 기록도 보존한다: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38548451513
- Windows 전체 회귀 **327 passed**, 가상 데모 통과.
- 오프라인 REST 145·보드 23·Ruff/format·production 타입 0 errors·verifier 통과.
- 사용자 PC 실증(제출·연결 확인)은 미실행이다.

## R05 거절 메시지 원격 CI — 2026-10-14, PR #9 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38554188630 (head `3eb2c3f`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/9 (squash 병합, main `66061fd`)
- Windows 전체 회귀·오프라인 REST·보드·Ruff/format·타입 검사 통과.
- 사용자 PC 재제출(거절 사유 확인)은 미실행이다.

## R05 첫 실증 결과 — 2026-10-14 저녁, 사용자 PC

- 명령: `submit_paper_buy --symbol 403870 --price 56600 --confirm-execute`.
- 결과: `order_submitted:true`, `acked:false`, `broker_code:20`,
  `broker_message:모의투자 종료`. 전송·판정·보고 경로 정상, 거절은 환경 사유다.
- 연결 확인은 4건 0행 `LINKAGE_UNCONFIRMED` 그대로다. Q01/Q02/Q08 미확정 유지.

## R05 배치 실행 검증 — 2026-10-14, `feature/rest-r05-demo-bat`

- `run-paper-demo.bat` 신규. 키 미설정 종료·연결 확인·실패 분기·바탕화면 로그를
  더미 키로 검증했고 값 노출 없음을 확인했다. 테스트 로그는 삭제했다.
- CMD `echo` 문구 안 괄호가 `if` 블록을 깨뜨리던 문제와 `Tee-Object -Append`
  순서 문제를 수정했다.
- basedpyright 로컬 미설치로 미검증, 원격 CI에서 확인한다. 예약 등록은 사용자 실행이다.

## R05 배치 원격 CI — 2026-10-14, PR #10 병합 완료

- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38579998229 (head `87b35b1`, success)
- PR: https://github.com/breadday/CherryPulse-KR-01/pull/10 (squash 병합, main `58820f3`)
- Python 변경 없음. 예약 등록은 아래 사용자 실행이다.

## R045 진단 보강 — 2026-10-22

실행 기준: main `4678173`, Windows Python 3.10.8 32-bit.

- 정규장 예약 manifest `results/r045-20261022/manifest.json`: PREWARM exit 0, READ_BEFORE exit 0, QUOTE_WS exit 1, `ABORTED`. 주문 제출 단계는 실행되지 않았다.
- 원본 log는 실행 시작·종료 코드만 남기며, manifest에는 stdout/stderr 바이트 수만 있어 구체적인 WebSocket `reason` 복구가 불가능했다.
- R045 runner는 probe JSON의 안전한 allowlist 요약만 manifest에 보존하도록 추가했다. stderr, 토큰 등 임의 필드는 쓰지 않는다. 회귀 테스트는 민감 필터와 실패 시 주문 단계 미호출을 검증한다.
- 검증: `py -3.10-32 -m pytest -q` **344 passed**; `py -3.10-32 -m pytest --confcutdir=tests/rest tests/rest -q` **161 passed**; verifier **exit 0 / 6 checks**, Ruff check/format, basedpyright (**0 errors**), Node board **35 passed**, `py check.py`, `git diff --check` 통과.
- verifier scope는 오프라인 REST/보드다. 실제 broker 계좌·WebSocket·주문을 검증하지 않았다. R04/R05 미완료와 `orders_enabled=false` 유지.
- TASK-3은 보드 CRUD 서버 계약 부재, TASK-4는 iOS/Android 실기기 접근 부재로 차단 상태. 원격 push/CI 결과는 이 기록 작성 시점에는 아직 미확인이다.

## 실패 단계 진단 구현 — 2026-10-22

- `StreamCapture`와 `probe_kiwoom_ws`가 실패 단계와 제한된 범주 코드만 출력한다. 예약 runner는 명시된 허용 목록만 manifest에 저장하며 임의 문자열을 버린다.
- TDD: 추가 테스트에서 token/connect 실패의 stage/kind 및 민감 메시지 비노출을 먼저 확인해 RED, 구현 후 GREEN.
- 검증: 전체 pytest **347 passed**; REST verifier **exit 0 / 6 checks**(REST tests 164; Ruff check/format; basedpyright 0 errors; Node board 35); `py check.py`; `git diff --check` 모두 통과.
- 이 결과는 오프라인 검사다. 실제 broker 접속·계좌·주문·실기기 검증은 수행하지 않았고 R04/R05는 미완료다.
- GitHub PR #14 run `39742233308`: `offline-rest` 및 `windows-engine` 성공. PR 병합 상태는 별도 확인 전이다.
