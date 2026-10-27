# HERMES TASK 2026-10-19 — 실행 결과

실행 기준: `main`, 작업 시작 당시 HEAD `379db6e`. 실제 계좌·주문·배포 권한과 증거가 필요한 항목은 소프트웨어 검사와 분리한다.

## TASK-1 — 경로 정합성: 완료

- `AGENTS.md`의 HANDOFF/STATUS 경로를 `docs/treadding/` 아래 실제 경로로 고쳤다.
- `check.py`에서 루트 엔진 파일을 필수 활성 파일 목록에서 제외하고, `back/legacy-2026-09-13/` 보관본이 있는 경우 `DEPRECATED`로 표시한다. 네 보관본을 모두 확인했다.
- `check.py`가 자신의 `from back`/`import back` 검사 문자열을 활성 import로 오인하던 오탐을 제외했다.
- `py check.py`: 필수 문서 6개와 보관본 4개 모두 확인, `❌ 미진행` 및 back import 경고 0건.
- 회귀 테스트 추가: `tests/test_check_script.py` 1 passed.

## TASK-2 — R04: 오프라인 검증 6/6 통과(2026-10-20), 실증 미완료

- 당시 지정 Python 확인: Python 3.10.8, 32-bit. 이는 검증 호스트 기록이며 REST 아키텍처 요건이 아니다. REST/WS는 32/64비트 모두 가능하고 현재 R045는 `py -3.10`을 사용한다. 32비트 요건은 OCX/COM 검사에만 적용한다.
- 2026-10-19 실행: verifier `passed:false` — `python -m basedpyright`가 32비트 환경에서 nodejs-wheel 빌드 실패로 인한 호출 방식 문제였다.
- 2026-10-20 수정: `docs/DEVELOPMENT-ENVIRONMENT.md`가 정한 `node .tools/typecheck/basedpyright/index.js` 진입점 사용. `.tools/typecheck`에 basedpyright 1.40.1 재설치. verifier가 로컬 node 진입점/CI `-m` 폴백을 선택하도록 `typecheck_command()` 도입.
- 2026-10-20 결과: `py -3.10-32 tools/verify_rest_migration.py` **exit 0, passed=true, 6/6 OK** — REST pytest 150 passed(신규 러너 테스트 5종 포함), ruff check/format 통과, basedpyright 0 errors, 보드 Node 35 passed, `git diff --check` 통과. `results/rest-migration-verification.json` 갱신.
- 회귀 테스트 `tests/rest/test_verify_runner.py` 추가: RED 5 failed → GREEN 5 passed. 전체 `pytest -q` 333 passed.
- 2026-10-19 23:22 KST 실행 시 정규장 밖이었다. 모의 계좌 조회, WebSocket 장중 수신, 1주 지정가 제출 및 주문 연결 실증은 실행하지 않았다. 주문 호출·계좌 증거는 없다.
- R04는 `LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`로 유지한다. `known_baseline`은 변경하지 않았다.

## TASK-3 — 보드 REST 연결: 차단

- 저장소에서 `/boards`, `/items`, `/patterns` 서버 라우트 또는 이를 구현한 API 명세를 찾지 못했다. 현재 `board.js`는 브라우저 초안 저장 흐름이며 REST `fetch` 호출이 없다.
- `REBUILD-02-CONTRACTS.md`는 주문·체결 실행 계약이고 이 보드 CRUD API의 인증·호스트·요청/응답·버전 충돌 계약을 정의하지 않는다.
- 서버 계약을 추측해 호출을 추가하지 않았다. R08은 `BOARD_DRAFT_LINK_PREVIEW_VERIFIED_ENGINE_ACCEPTANCE_PENDING`으로 유지한다.

## TASK-4 — 모바일 실기기 6/6: 차단

- 이 실행 환경에서 iOS Safari 및 Android Chrome 실기기 조작을 할 수 없어 체크리스트를 수행하지 않았다.
- 기존 PC 브라우저 6/6 기록은 실기기 결과로 승격하지 않는다. `docs/D02-BOARD-PROGRESS.md`의 실기기 pending 상태를 유지한다.

## 전체 검증 및 미수행

- `py -3.10-32 -m pytest -q --tb=line`: 328 passed.
- `node --test web/board/board.test.js web/board/buy-preview.test.js web/board/log-view.test.js`: 35 passed.
- `py check.py`: 성공, 필수 항목 누락·보관본 누락·활성 back import 경고 없음.
- `git diff --check`: 통과.
- 실제 계좌 조회·WebSocket·주문, 보드 서버 API 연동, 물리 모바일 검증, 커밋·push는 수행하지 않았다.

## 2026-10-22 예약 실행 및 개발 후속

- `results/r045-20261022/manifest.json`: PREWARM exit 0, READ_BEFORE exit 0, QUOTE_WS exit 1, 최종 `ABORTED`. `ORDER_PREVIEW`/`ORDER_SUBMIT` 단계가 없으므로 오늘 주문 제출은 없었다.
- `results/r045-morning-run.log`에는 시작·종료 코드만 있고 manifest에는 probe stdout 내용이 저장되지 않아, WebSocket의 구체적인 `reason`을 기존 실행에서 복구할 수 없다. 실패 원인은 아직 미확정이다.
- R045 실행기는 이후 실행에서 probe의 JSON 요약 중 reason/연결·관측 수/신선도/마스킹된 상태 bool만 manifest에 저장하도록 수정했다. 임의 출력과 stderr는 저장하지 않는다. 회귀 테스트는 민감 필드가 제외되고 WS 실패 뒤 주문 제출 명령이 호출되지 않는지 확인한다.
- R04는 `LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`, R05는 오프라인 도구 검증만 완료 상태로 유지한다. 실제 모의계좌·WebSocket·주문·사후 연결 증거는 확보되지 않았다.
- TASK-3은 `/boards`, `/items`, `/patterns` CRUD 계약/서버 구현 부재로 계속 차단. TASK-4는 iOS/Android 실기기 접근이 필요해 대기. 사용자 제공 서버 명세와 실기기 검증이 필요하다.
- 예약 작업 `CherryPulse-R045-Demo`는 평일 09:30 활성 상태다. 다음 실행은 2026-10-23 09:30이며, 점검 성공 시 기존 승인 범위의 모의 1주 지정가 단계까지 진행할 수 있다. 예약 설정은 변경하지 않았다.
