# REST 전환 작업 인계

갱신일: 2026-11-13

## 현재 기준

- 공식 REST API 및 WebSocket 경계를 기준으로 개발한다. 이전 개발 방향·계획·검증 기록은 `docs/reference/legacy-development/`에 참고용으로 보관하며 활성 개발 지시로 사용하지 않는다.
- 프로젝트 런타임은 64-bit Python 3.15 (`>=3.15,<3.16`)이다. CI와 R045 실행기도 동일한 격리 환경을 사용한다.
- 최종 결정: COM/ActiveX CLI 네 개는 REST-only 진입점에서 fail-closed로 종료한다. REST 조회와 WebSocket 도구는 유지하며 기본 오프라인 모드다. COM control 생성에는 REST 대체가 없다.
- REST 오프라인 검증은 완료했지만 증권사 계좌·실시간 시세·주문·Windows 운영 엔진 인수는 미완료다.
- `orders_enabled=false`를 유지한다. 실주문·모의주문·예약 작업 실행은 이번 변경에서 호출하지 않았다.
- 기존 변경 중 REST 런타임 전환과 무관한 파일은 사용자 작업으로 간주하고 보존한다. 커밋할 때는 의도된 파일만 선별한다.

## 로컬 확인된 검증

- Python 3.15.2 x64 전체 회귀: `373 passed`.
- REST 오프라인 verifier: `6/6`, 포함된 REST 테스트 `168 passed`, Ruff check/format 통과, REST adapter basedpyright `0 errors`.
- Worker 및 보드 Node 테스트: `63 passed`.
- `npm run build`: Wrangler dry-run 성공; 운영 배포 아님.
- `git diff --check`: 통과.
- 전체 회귀의 ResourceWarning을 유발한 세 테스트에서 SQLite connection close 처리를 명시적으로 보완했다.

## 미완료·차단

1. `bd67c5b09e22c5b43d9aee53816cf3a377940838`를 `origin/main`에서 확인했다. GitHub Actions REST migration run `41462431000` 및 두 job은 성공했다.
2. 별도 Supabase Preview check는 `Remote migration versions not found in local migrations directory.`로 실패했다. 커밋에는 migration 파일 변경이 없고, 원격 이력 조회·repair·DB 변경은 하지 않았다. Supabase 담당자가 원격과 저장소 migration 이력을 대조해야 한다.
3. 증권사 실측, 계좌 대조, WebSocket 장중 수신, 주문 실증은 별도 사용자 환경·승인이 필요하며 소프트웨어 검사로 승격하지 않는다.

## 재개 명령

```powershell
.venv-rest\Scripts\python.exe -m pytest -q --tb=short
.venv-rest\Scripts\python.exe tools\verify_rest_migration.py
node --test cloud/worker.test.mjs web/board/*.test.js
npm run build
```

최종 확인: 로컬 Python·REST·Node 검증과 GitHub Actions REST migration workflow는 통과했다. 별도 Supabase Preview check는 원격 migration 버전 불일치로 실패하여 저장소/원격 상태 대조가 남아 있다. 실제 브로커 검증은 미완료이며 `orders_enabled=false`다.

## 2026-11-04 R04 오프라인 미매핑 보유 행 가드

- `RestReadBatch`는 완전한 조회 묶음에서도 broker 보유 행을 managed 원장에 편입하지 않는다. 행이 있으면 개수와 `BROKER_POSITIONS_UNMAPPED`를 보고하고, 행이 없으면 `BROKER_IDENTITY_MAPPING_UNVERIFIED`를 유지한다. 잘못된 행 형식은 `POSITION_ROWS_UNCONFIRMED`로 닫는다.
- 실제 계좌 identity mapping·외부 보유 판정·원장 연결은 여전히 미완료다. 합성 응답 외의 브로커 호출은 하지 않았고 `can_reconcile=false`, `orders_enabled=false`를 유지했다.
- TDD RED에서 새 행 수 속성이 없어 실패한 뒤 구현했다. 최종 확인: 전체 pytest `374 passed`; REST verifier `6/6` (REST pytest `169 passed`, Ruff check/format 통과, adapter basedpyright `0 errors`); Worker/board Node `63 passed`; `npm run build` dry-run과 `git diff --check` 통과.
- `uv lock --check`는 `uv` 실행 파일이 현재 PATH에 없어 exit 127로 확인하지 못했다. 의존성·잠금 파일은 변경하지 않았다. 기존 사용자 변경 파일과 미추적 테스트를 보존했다. 이번 요청에서 커밋·push는 하지 않았다.
- 다음: 지정 PC에서 사용자 승인 후 R04 읽기 전용 체크리스트의 마스킹된 실행 결과를 확보한다. 그 전까지 R04 live 상태 및 주문 OFF를 유지한다.

## 2026-11-05 저장소 전체 Ruff 정리

- 전체 Ruff check 통과, `ruff format --check .` 162 files already formatted.
- Python 전체 pytest 374 passed; REST verifier 6/6 (REST pytest 169, Ruff check/format, adapter basedpyright 0 errors); Worker/board Node 63 passed; build dry-run 및 `git diff --check` 통과.
- 기존 변경 파일과 두 미추적 테스트를 보존했다. 커밋·push·배포·브로커 호출은 하지 않았다. `orders_enabled=false` 유지.
- 다음 소프트웨어/실증 게이트는 계속 R04 지정 PC 읽기 전용 검증이다. 실제 계좌 식별과 장중 WebSocket 수신을 사용자 승인·마스킹된 근거로 확인하기 전까지 R04 live 및 `can_reconcile=false`를 유지한다.
- 앞서 `uv`가 PATH에 없어 검사하지 못했던 lock 검증은 `.venv-rest/Scripts/uv.exe`에서 실행 가능함을 확인했다. `uv 0.12.13`의 `uv lock --check`가 exit 0으로 통과했다.

## 2026-11-06 PAPER R04/R05 실측 및 runner 수정

- 사용자 요청에 따라 승인된 `067310` 1주 모의 주문 runner를 1회 실행했다. `ORDER_ACKED`, 가격 24,700; 사전 조회 5건 complete, 장중 WS 24 quotes/fresh true.
- 조회 당시 broker 보유 1행이 미매핑으로 남아 있고 `account_reconciled=false`다. 올바른 종목으로 재조회한 사후 linkage도 `LINKAGE_UNCONFIRMED`; HTS에서 접수 주문의 미체결/체결 상태를 확인하기 전 추가 주문·수정·취소는 하지 않는다.
- 원인: R045 runner가 사후 linkage 확인 시 기본 종목 `005930`을 사용했고, 검사 실패 후에도 manifest status를 `DONE`으로 썼다. TDD 회귀를 먼저 실패시킨 뒤 현재 종목 전달과 `PARTIAL_POST_ORDER_CHECKS_UNCONFIRMED` status 처리를 적용했다.
- 수정 후 Python 전체 380 passed, REST verifier 6/6 (REST 171; adapter basedpyright 0 errors), 전체 Ruff pass, format 165 files, Node 63 passed, build dry-run, uv lock check, diff check 모두 통과.
- 주문 sentinel 및 runner manifest는 `results/` 아래 있다. 주문 식별자 원문은 보관 문서에 복사하지 않았다. `orders_enabled=false`, `can_reconcile=false` 유지.
- 2026-11-09 사용자가 HTS 캡처를 제공했다. [0343] 기간별 주문체결상세는 11/06 067310 1주 체결(평균 24,700, 12:54:35)을 표시했고, [0341]은 067310 전체 미체결 조회 완료 후 결과가 비어 있었다. [0351] 당일 빈 결과는 과거 체결 근거가 아니다.
- HTS 근거로 접수 및 체결, 캡처 조회 시점의 미체결 없음은 확인했지만 REST history linkage/Q01 다중 일치는 `LINKAGE_UNCONFIRMED`다. R04 보유 1행 identity도 미매핑이므로 `account_reconciled=false`, `can_reconcile=false`, `orders_enabled=false` 유지.
- 다음은 기록된 HTS 체결과 REST history linkage 간 차이를 로컬 코드/저장 증거로 읽기 전용 분석한다. 추가 브로커 조회나 주문·정정·취소는 하지 않고, R04/R05 완료로 승격하지 않는다.

## 2026-11-10 진행 상태 및 범위 결정

- 사용자가 iOS 실기기 인수를 범위에서 제외했다. Android Chrome 실기기 6/6만 남기며, 활성 계획·상태·보드 인계·체크리스트에서 iOS 항목을 제거했다. `docs/reference/legacy-development/`는 당시 기록을 보존하는 역사 자료이므로 수정하지 않는다.
- 2026-11-09 사용자의 요청으로 `CherryPulse-paper-demo`, `CherryPulsePaperDemo`, `CherryPulse-R045-Demo`, `CherryPulseFIDMorning`을 삭제했다. Windows Task Scheduler에 CherryPulse 작업은 없으며 새 작업을 등록하지 않는다.
- 로컬 manifest에서 2026-11-06 실행의 top-level `DONE`과 `LINKAGE` exit 1 / `LINKAGE_UNCONFIRMED`가 함께 확인됐다. 이는 현재 runner 수정 전의 과거 산출물이며, 당시 원문 행/주문 식별자는 저장되지 않아 정확한 linkage 원인을 재구성할 수 없다.
- 현재 runner의 사후 검사 실패 처리와 새 안전 요약 진단 저장 회귀를 포함한 집중 테스트 `23 passed`를 확인했다. 향후 manifest에는 고정된 4개 query의 행/고유 주문 개수와 linkage 판정 bool만 저장하며 식별자·원문 응답·stderr는 저장하지 않는다. 테스트는 합성·오프라인 검증이며 브로커 상태 확인이 아니다.
- 로컬 검증: 전체 pytest `381 passed`; REST verifier `6/6` 및 REST pytest `172 passed`; Ruff check/format 통과; REST adapter basedpyright `0 errors`; Node `63 passed`; `npm run build` dry-run 성공; `git diff --check` 통과. 실계좌·브로커·주문은 실행하지 않았다.
- 커밋 `a6cf0a2`를 `main`에 push했고 GitHub Actions run `42823659024`의 `offline-rest`, `windows-engine` 두 job이 모두 성공했다.
- 저장 결과로는 왜 다른 history endpoint가 같은 주문 행을 반환하지 않았는지 확정할 수 없다. 추가 조회 없이 원인 미확정을 유지하고, 별도 승인된 마스킹 증거가 없으면 `LINKAGE_UNCONFIRMED`, `account_reconciled=false`, `can_reconcile=false`, `orders_enabled=false`를 유지한다.

## 2026-11-11 64-bit-only 결정 및 COM CLI 퇴역

- 최종 런타임은 64-bit Python 3.15 `.venv-rest`다. REST/HTTP 및 WebSocket 구현은 유지했다.
- `verify_kiwoom_com.py`, `verify_kiwoom_connection.py`, `verify_kiwoom_readonly.py`, `tools/inspect_kiwoom_realtime.py`의 공개 CLI는 `COM_RETIRED_REST_ONLY`와 대체 경로를 출력하고 exit 2로 닫힌다. 직접 실행에서 PyQt5/OCX를 불러오거나 네트워크를 호출하지 않는다. 기존 COM 구현과 역사 문서는 참고용이며 `docs/reference/legacy-development/`를 수정하지 않았다.
- 대체: REST 조회는 `tools.probe_kiwoom_rest`, 시세 스트림은 `tools.probe_kiwoom_ws`; 둘 다 기본 오프라인이다. 실제 네트워크 읽기는 `--execute-read-only`의 명시적 opt-in과 별도 승인 전에는 하지 않는다. COM control 생성 및 구형 TR의 일대일 동등 대체는 없다.
- TDD에서 일반 모드 4건과 `-I` isolated 모드 4건을 먼저 실패 재현한 뒤, 두 실행 모드의 COM 진입점 8건과 집중 테스트 10건이 통과했다. 전체 pytest 388, Node 63, Ruff check/format 168 files, adapter basedpyright 0 errors, build dry-run 및 `git diff --check`가 통과했다.
- REST와 WebSocket 기본 CLI는 각각 `network=false`, `orders_enabled=false`를 반환했다. 네트워크·계좌·주문·예약 작업 변경은 하지 않았다.
- `.venv-rest`는 Python 3.15.2 x64다. 다만 `py -0p`에는 Python 3.10.8 32-bit가 여전히 등록되어 있다. 전역 Python 제거는 이 작업에서 하지 않았으므로 OS 수준 32-bit 제거는 완료로 단정하지 않는다.
- 2026-11-11 당시에는 커밋·push·CI 실행을 하지 않았다. 다음은 기존 R05/R04 로컬 linkage 분석이며, 필요하면 남은 전역 32-bit 설치의 정리는 별도 범위로 다룬다.

## 2026-11-12 호스트 Python 정리 및 전달 상태

- 사용자가 승인한 범위에서 등록된 정상 uninstaller로 사용자 전역 Python 3.10.8 32-bit를 제거했다. `py -0p`에는 프로젝트의 Python 3.15-64만 표시되고, `py -3.10-32`는 실행되지 않으며 제거 레지스트리 항목도 0개다.
- 제거 후 재검증: 전체 pytest `388 passed`; Node `63 passed`; Ruff check 및 format `168 files`; REST adapter basedpyright `0 errors, 0 warnings, 0 notes`; build dry-run 통과; REST/WS 기본 실행 각각 `network=false`, `orders_enabled=false`; `git diff --check` 및 상태 JSON 파싱 통과.
- 2026-11-12 당시에는 기존 사용자 변경을 보호하고 런타임/COM 퇴역 범위만 선별해 commit/push하겠다는 계획을 인계했으나 실제로 수행하지 않았다. 2026-11-13 사용자가 해당 범위의 commit/push를 명시 승인했다. 실계좌·주문·배포는 포함하지 않는다.

## 2026-11-13 COM 퇴역 진입점 강화 및 R04/R05 로컬 분석

- 독립 리뷰에서 직접 CLI는 종료되더라도 import 경로에 구형 PyQt/COM 구현이 남아 있음을 발견했다. 네 활성 진입점을 간결한 퇴역 stub으로 교체해 일반 import 및 isolated(`-I`) import 모두 PyQt/COM을 불러오지 않게 했다. `verify_kiwoom_readonly.py`는 구형 TR과 REST query가 동등하다고 암시하지 않도록 안내 문구를 조정했다.
- TDD 회귀는 수정 전 두 실행 모드에서 `ModuleNotFoundError: PyQt5`로 실패했고, 수정 후 `.venv-rest/Scripts/python.exe -m pytest tests/test_com_scripts_retired.py tests/test_realtime_probe.py -q --tb=short` 결과 `12 passed`다.
- 저장된 R05 자료만으로는 2026-11-06 API endpoint 간 행 차이를 복원할 수 없다. 안전한 manifest에는 집계 개수와 판정 bool만 있고 raw 응답 행/주문 식별자는 보존되지 않았다. HTS의 체결 확인은 유지하되 API linkage는 `LINKAGE_UNCONFIRMED`로 둔다.
- R04 `kt00018` 보유 1행은 실제 계좌·종목 identity에 연결되지 않았다. 계좌/종목 mapping 및 원장 대조는 미완료이며 `account_reconciled=false`, `can_reconcile=false`, `orders_enabled=false`다. 비밀정보나 계좌·주문 식별자를 채팅/문서에 옮기지 않는다.
- 추가 브로커 조회·주문·정정·취소·재전송, 예약 작업 변경 및 배포는 하지 않는다. 다음 가능한 소프트웨어 단위는 합성 테스트만 사용하는 R05 dispatcher의 SENDING/UNKNOWN/부분체결/취소경합/재시작 경계이며, 구현 전후에도 주문 OFF를 유지한다.
- 별도 외부 인수 미완료: R04 identity 근거, R05 API linkage 증거, Android Chrome 실기기 6/6, 확정 보드 REST API 호스트·인증·CRUD 계약, Supabase 원격 migration 이력 대조, Windows 운영 엔진 인수.
- 커밋 `6c39e1d12d0c765c60cefb5313279e1e4a0688fd`를 `origin/refactor/kiwoom-rest`에 push했고 원격 ref를 재확인했다. GitHub Actions REST migration verification run `#93`은 성공했다. 기존 PR `#3`은 이 커밋 이전에 이미 merge된 상태였으므로 이번 커밋은 `main`에 merge되지 않았고, 별도 merge는 수행하지 않았다.
