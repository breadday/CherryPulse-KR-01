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

- CI 설정은 Python 3.15로 변경했으나, 이번 로컬 세션에서 GitHub Actions 실행 결과는 아직 없다.
- 증권사 인증·계좌 조회·WebSocket 장중 데이터는 호출하지 않았다.
- 주문·취소·운영 DB 변경·예약 실행·배포는 수행하지 않았다.
- 따라서 broker verification과 Windows 운영 엔진 인수는 미확인이다. `orders_enabled=false`를 유지한다.

## 다음 완료 조건

활성 개발 문서와 실행 스크립트의 REST 전환 및 참고 자료 이동을 마친 뒤 전체 로컬 검증을 반복한다. 의도된 파일만 한글 커밋으로 push하고 원격 CI 성공을 확인한 다음 이 문서를 갱신한다.
