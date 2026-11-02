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
