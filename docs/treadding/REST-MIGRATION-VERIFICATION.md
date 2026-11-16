# REST 오프라인 검증 기록

갱신일: 2026-11-13

## 이번 로컬 검증

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| Python 전체 회귀 | Python 3.15.2 x64, `python -m pytest -q --tb=short` | 373 passed | 저장소 Python 테스트 |
| REST verifier | `python tools/verify_rest_migration.py` | exit 0, 6/6 | REST 테스트 168, Ruff check/format, REST adapter basedpyright 0 errors, 보드 Node 테스트, diff check |
| Worker·보드 | `node --test cloud/worker.test.mjs web/board/*.test.js` | 63 passed | 로컬 합성·회귀 검사 |
| 빌드 | `npm run build` | dry-run 성공 | Wrangler `--dry-run`; 배포하지 않음 |
| 공백 검사 | `git diff --check` | 통과 | 작업 트리 |

테스트에서 발견한 SQLite connection 미종료 경고는 관련 테스트 세 곳에서 연결 종료를 보장하도록 고쳤다. 전체 회귀 재실행 결과 373개가 모두 통과했다.

## CI·운영 검증 구분

- `bd67c5b09e22c5b43d9aee53816cf3a377940838`를 `origin/main`에서 확인했다. GitHub Actions REST migration run `41462431000`은 성공했고 `offline-rest`, `windows-engine` 두 job 모두 성공했다.
- 별도 Supabase Preview check는 실패했다: `Remote migration versions not found in local migrations directory.` 현재 로컬에는 SQL migration 3개가 있고 이번 커밋에는 `supabase/` 또는 SQL 변경이 없다. 실패 세부정보에서 누락된 원격 migration 버전은 확인되지 않았다.
- 원격 migration history 조회, repair, DB 변경 또는 재배포는 수행하지 않았다. 이 불일치는 Supabase 프로젝트 담당자가 원격 이력과 저장소를 대조해야 한다.
- 증권사 인증·계좌 조회·WebSocket 장중 데이터는 호출하지 않았다. 주문·취소·예약 실행은 수행하지 않았고 `orders_enabled=false`를 유지한다.
- Python 3.15.2에서 변경된 REST auth/WebSocket 어댑터의 compile/import와 집중 테스트 39개도 통과했다.

## 다음 완료 조건

로컬 REST 전환 및 주 CI 검증은 완료했다. Supabase Preview 실패는 원격 migration 상태 대조가 필요한 별도 차단 항목으로 남긴다. broker verification과 Windows 운영 엔진 인수는 미확인이다.

## 2026-11-04 R04 오프라인 경계 회귀

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| Python 전체 회귀 | Python 3.15.2 x64, `python -m pytest -q --tb=short` | 374 passed | 저장소 Python 테스트 |
| REST verifier | `python tools/verify_rest_migration.py` | exit 0, 6/6 | REST pytest 169, Ruff check/format, adapter basedpyright 0 errors, board Node tests, diff check |
| Worker·보드 | `node --test cloud/worker.test.mjs web/board/*.test.js` | 63 passed | 로컬 합성·회귀 검사 |
| 빌드 | `npm run build` | dry-run 성공 | 배포하지 않음 |
| 공백 검사 | `git diff --check` | 통과 | 작업 트리 |

R04의 완전한 합성 조회에 broker position 행이 있을 때 미매핑 행 개수만 보고하고 가상 원장 대조를 허용하지 않는 회귀를 추가했다. 실제 broker read, 계좌 식별, 주문·취소 및 배포는 하지 않았다. `uv lock --check`는 `uv`가 PATH에 없어 exit 127로 미확인했으며 잠금 파일은 변경하지 않았다.

## 2026-11-05 저장소 전체 Ruff 정리 및 재검증

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| 전체 Ruff | `.venv-rest/Scripts/python.exe -m ruff check .` | 통과 | 저장소 전체 |
| 전체 포맷 | `.venv-rest/Scripts/python.exe -m ruff format --check .` | 162 files already formatted | 저장소 전체 |
| Python 전체 회귀 | Python 3.15.2 x64, `.venv-rest/Scripts/python.exe -m pytest -q --tb=short` | 374 passed | 저장소 Python 테스트 |
| REST verifier | `.venv-rest/Scripts/python.exe tools/verify_rest_migration.py` | exit 0, 6/6 | REST pytest 169, Ruff check/format, adapter basedpyright 0 errors 등 |
| Worker·보드 | `node --test cloud/worker.test.mjs web/board/*.test.js` | 63 passed | 로컬 테스트 |
| 빌드 | `npm run build` | dry-run 성공 | 배포하지 않음 |
| diff 검사 | `git diff --check` | 통과 | 작업 트리 |
| 의존성 잠금 | `.venv-rest/Scripts/uv.exe lock --check` (`uv 0.12.13`) | exit 0 | `uv.lock` 확인, 변경 없음 |

Ruff 규칙을 저장소 전체에 적용하고 Pydantic이 런타임에 사용하는 타입 import는 런타임에 유지했다. 미커밋 기존 변경은 그대로 보존했다. 이 검증은 실계좌·장중 WebSocket·주문 증거를 제공하지 않으며 R04/R05 승격 근거로 사용하지 않는다. `orders_enabled=false` 유지.

## 2026-11-06 R045 실측 및 linkage 회귀 수정

- 지정된 PAPER 실행기에서 R045 runner를 사용자 요청으로 1회 실행했다. 사전 REST 5건 완전, WebSocket 24 quotes/fresh true, 1주 지정가 `ORDER_ACKED`; 원문 식별자 없이 결과는 `REST-R05-ORDER-DEMO.md`에 기록했다.
- Runner 사후 linkage가 기본 종목을 쓰는 버그와 실패를 `DONE`으로 표시하는 문제를 발견했다. TDD RED 재현 후 현재 종목 전달 및 사후 검사 미확정 status 처리를 수정했다.
- 올바른 종목의 실측 linkage 결과는 여전히 `LINKAGE_UNCONFIRMED`; HTS 주문 상태 확인 전 재주문·수정·취소하지 않는다. R04 계좌 identity mapping 및 reconciliation은 미확정.
- 수정 후 Python 전체 회귀 `380 passed`; REST verifier `6/6` (REST pytest `171 passed`, adapter basedpyright `0 errors`); 전체 Ruff check 통과, 전체 format `165 files already formatted`; Worker/board Node `63 passed`; build dry-run, uv 0.12.13 `lock --check`, `git diff --check` 통과.
- 이 검증은 PAPER 경로만 사용했으며 live-order API나 배포는 실행하지 않았다. `orders_enabled=false`, `account_reconciled=false`, `can_reconcile=false` 유지.

## 2026-11-11 64-bit-only COM CLI 퇴역 검증

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| 런타임 | `.venv-rest/Scripts/python.exe`, Python 3.15.2 | 64-bit | 프로젝트 실행 환경 |
| COM CLI 퇴역 회귀 | `pytest tests/test_com_scripts_retired.py tests/test_realtime_probe.py -q` | 10 passed | 네 진입점이 일반/isolated(`-I`) 모드에서 안내 후 exit 2 |
| Python 전체 회귀 | `.venv-rest/Scripts/python.exe -m pytest -q --tb=short` | 388 passed | 오프라인 저장소 테스트 |
| Ruff | `ruff check .`; `ruff format --check .` | 통과; 168 files | 저장소 전체 |
| 타입 검사 | basedpyright REST adapters | 0 errors, 0 warnings | REST adapter 범위 |
| Node | `npm test` | 63 passed | Worker/보드 |
| 빌드 | `npm run build` | dry-run 성공 | 배포하지 않음 |
| REST/WS 기본 모드 | `python -m tools.probe_kiwoom_rest`; `python -m tools.probe_kiwoom_ws` | 모두 `network=false`, `orders_enabled=false` | 실제 네트워크 미호출 |
| diff 검사 | `git diff --check` | 통과 | 작업 트리 |

레거시 진입점은 64-bit REST 전용 경로에서 fail-closed로 처리하며, REST/WS 도구를 사용한다. 2026-11-11 검증 시점에는 WebSocket 실측·계좌 조회·주문·예약 작업 변경·배포·commit/push·CI를 수행하지 않았다. 당시 `py -0p`에는 Python 3.10.8 32-bit가 남아 있었다.

## 2026-11-12 호스트 런타임 정리 확인

| 확인 | 결과 |
|---|---|
| Python 3.10.8 32-bit 제거 | 등록된 사용자 전역 Python uninstaller exit 0 |
| `py -0p` | 프로젝트 Python 3.15-64만 표시 |
| `py -3.10-32` | 더 이상 실행되지 않음 |
| `Uninstall` 레지스트리 | Python 3.10.8 항목 0개 |
| 프로젝트 `.venv-rest` | Python 3.15.2, 64-bit로 실행됨 |

제거 후 전체 pytest `388 passed`, Worker/board Node `63 passed`, Ruff check 및 format `168 files`, REST adapter basedpyright `0 errors, 0 warnings, 0 notes`, build dry-run, REST/WS 기본 오프라인 실행, `git diff --check`, 상태 JSON 파싱이 통과했다. 원격 CI는 push 후 확인한다. 이 호스트 정리는 프로젝트 전용 `.venv-rest`를 변경하지 않았다.

## 2026-11-13 퇴역 COM 진입점 import-safety 보강

독립 리뷰가 기존 direct-CLI guard 뒤에 남은 COM 구현의 import 경로를 찾아냈다. 네 진입점을 COM/PyQt 의존성이 없는 퇴역 stub으로 바꾸고 import safety 회귀를 추가했다. 수정 전 normal/isolated 두 경우 모두 PyQt import 실패로 재현됐고, 수정 후 `.venv-rest/Scripts/python.exe -m pytest tests/test_com_scripts_retired.py tests/test_realtime_probe.py -q --tb=short` 결과 `12 passed`.

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| Python 전체 회귀 | `.venv-rest/Scripts/python.exe -m pytest -q --tb=short` | 390 passed | 저장소 오프라인 테스트 |
| REST verifier | `python tools/verify_rest_migration.py` | 6/6, REST 172 passed | REST scope, Ruff, typecheck 및 Node subset 포함 |
| Ruff | `ruff check .`; `ruff format --check .` | 통과; 168 files | 저장소 전체 |
| REST adapter 타입 검사 | basedpyright | 0 errors, 0 warnings, 0 notes | REST adapter 범위 |
| Node | `node --test cloud/worker.test.mjs web/board/*.test.js` | 63 passed | Worker/board |
| 빌드 | `npm run build` | dry-run 성공 | 배포 아님 |
| diff | `git diff --check` | 통과 | 작업 트리 |

R04 보유 행 identity와 R05 API linkage는 여전히 증거 부족이다. 기존 2026-11-06 raw query rows/주문 식별자가 저장되지 않아 endpoint 차이의 정확한 원인은 재구성할 수 없다. 이 검증은 오프라인 코드 검사이며 broker/account/Windows-engine acceptance는 `false`다. 추가 조회·주문·예약 실행·배포는 하지 않았다.

## 2026-11-13 commit·push 및 CI 확인

- `6c39e1d12d0c765c60cefb5313279e1e4a0688fd`를 `origin/refactor/kiwoom-rest`에 push했고 `git ls-remote`에서 원격 branch SHA가 일치하는 것을 확인했다. GitHub Actions REST migration verification run `#93`은 성공했다.
- 기존 PR `#3`은 이 커밋 이전에 이미 merge되어 있었다. 이번 커밋은 feature branch에만 있으며 `main`은 기존 SHA에 그대로다. merge 또는 새 PR 생성은 하지 않았다.

## 2026-11-16 R05 recovery 회귀 검증

| 구분 | 명령/환경 | 결과 | 범위 |
|---|---|---:|---|
| Python 전체 회귀 | `.venv-rest/Scripts/python.exe -m pytest -q --tb=short` | 391 passed | 저장소 Python 테스트 |
| R05 내구성/preflight | `pytest tests/test_durability.py tests/test_dispatch_preflight.py -q` | 15 passed | 합성 원장·복구 경계 |
| REST verifier | `python tools/verify_rest_migration.py` | exit 0, 6/6 | REST pytest 172, Ruff, basedpyright, Node 39 및 diff 검사 |
| 변경 파일 Ruff | `ruff check` 및 `ruff format --check` (`execution/virtual.py`, `tests/test_durability.py`) | 통과 | 수정 대상 파일 |
| diff 검사 | `git diff --check` | 통과 | 작업 트리 |

재시작 때 `RECONCILING` 사실을 반복 append하던 것을 막고, unresolved 상태 반환과 재전송 금지 동작은 유지했다. 모든 검사는 오프라인 합성 테스트다. broker verified와 Windows 운영 엔진 verified는 false이며 `orders_enabled=false`를 유지한다. 별도 작업 트리의 사용자 변경은 검증 범위에 포함하지 않았고 staging하지 않았다.

## 2026-11-17 기존 변경 오프라인 검증 재개

- 기준 커밋 `a7ae21cdfa18a1b1270223b5c332e031229f9307`, 브랜치 `refactor/kiwoom-rest`. 검증 시작 시 변경 67개(추적 파일 61, 미추적 6, staged 0). 소스·테스트 수정, 새 테스트, stage/commit/push는 하지 않았다.
- 변경 파일과 인접 REST runner 검증을 먼저 수행했다. 저장소 루트에서 프로젝트 Python 3.15 환경으로 `pytest -q --tb=short -p no:cacheprovider --basetemp <profile scratch> <변경 테스트와 REST runner 관련 29개 파일>`: **241 passed**. 그 다음 전체 `pytest -q --tb=short -p no:cacheprovider --basetemp <profile scratch>`: **392 passed**. 자격 증명 관련 환경 변수와 `PYTHONPATH`는 하위 프로세스에서 제거했다.
- 저장소 루트에서 `ruff check .`: **All checks passed** (Python 3.15 지원 단계 안내 경고만 표시). `ruff format --check .`: **169 files already formatted**. Ruff cache는 profile scratch로 분리했다.
- `node .tools/typecheck/basedpyright/index.js --pythonpath .venv-rest/Scripts/python.exe adapters/kiwoom_rest*.py`: **0 errors, 0 warnings, 0 notes**. `pyproject.toml`의 전체 `execution`/`tests` 타입 검사 범위는 실행하지 않았다. `REST-MIGRATION-STATUS.json`에 255개 기존 기준 오류가 기록되어 있어 이 작업에서는 migration verifier의 adapter 범위만 검사했다.
- `node --test cloud/worker.test.mjs web/board/*.test.js`: **67 passed**.
- `node node_modules/wrangler/bin/wrangler.js deploy --dry-run --outdir <profile scratch>/wrangler-local-build/output`: Wrangler 4.152.0 dry-run 성공, `web` 자산 23개 읽음. 배포하지 않았다.
- `git diff --check`: 통과. Git의 LF→CRLF 변환 경고만 있었으며 파일을 수정하지 않았다.
- `tools/verify_rest_migration.py`는 기존 `results/rest-migration-verification.json`을 원자적으로 덮어쓰는 구현이어서 실행하지 않았다. 대신 해당 runner의 오프라인 검사와 겹치는 테스트·Ruff·format·adapter typecheck·Node·diff 검사를 직접 실행했고, 전체 pytest도 통과했다. Wrangler 출력은 repo 밖 scratch로 보냈다.
- 잘못된 작업 디렉터리에서 실행된 선행 Ruff/basedpyright/Wrangler 호출은 이 검증 결과로 세지 않았다. 이후 프로젝트 루트를 명시해 다시 실행한 결과만 위에 기록했다. 재확인 시 해당 Ruff 프로세스는 이미 종료되어 있었으며 어떤 프로세스도 종료하지 않았다. 남은 프로젝트 관련 프로세스는 loopback 주소에 `web`만 제공하는 읽기 전용 `python -m http.server`였다.
- 최종 `git status --short --untracked-files=all`은 68개(추적 변경 62, 미추적 6, staged 0)다. 시작 당시 67개에 요청된 이 검증 기록 `docs/treadding/REST-MIGRATION-VERIFICATION.md` 1개가 추가되었고, 소스·테스트 변경은 없었다.
- 최초 ZIP 생성 스크립트 파일은 safe-root 쓰기 제한으로 생성되지 않았고, 그 실패가 ZIP 생성에는 영향을 주지 않았다. ZIP은 별도 inline Python 호출로 만들어졌다. 이후 갱신된 문서를 포함하도록 Git-ignored `results/local-recovery/` 아래 최종 복구 ZIP을 생성·검증했다. ZIP에는 변경 스냅샷 67개가 있고, 미추적 예약 작업 인벤토리 CSV 1개는 의도적으로 제외했다. 따라서 CSV는 ZIP에서 복구할 수 없는 미보존 변경으로 남으며, 원본은 저장소의 미추적 상태로 유지된다.
- 실제 broker/API·계좌·주문·정정·취소·재전송, 예약 실행/변경, 운영 배포는 하지 않았다. `orders_enabled=false`, `can_reconcile=false`, `account_reconciled=false`를 유지한다. 실 REST dispatcher는 미구현, PAPER API linkage는 미확정이다.
