# REST 전환 작업 인계

갱신일: 2026-11-02

## 현재 기준

- 공식 REST API 및 WebSocket 경계를 기준으로 개발한다. 이전 개발 방향·계획·검증 기록은 `docs/reference/legacy-development/`에 참고용으로 보관하며 활성 개발 지시로 사용하지 않는다.
- 프로젝트 런타임은 64-bit Python 3.15 (`>=3.15,<3.16`)이다. CI와 R045 실행기도 동일한 격리 환경을 사용한다.
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
