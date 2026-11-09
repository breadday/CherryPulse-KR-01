# REST 오프라인 검증 기록

갱신일: 2026-11-02

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
