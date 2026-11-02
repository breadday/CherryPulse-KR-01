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

1. 로컬 검증은 Python 373, REST verifier 6/6, Node 63, build dry-run, lock check 및 staged/unstaged diff check를 통과했다. 이번 작업 파일만 선별해 커밋한다.
2. 커밋을 push한 뒤 exact SHA의 GitHub Actions를 확인하고 이 문서와 상태 JSON을 갱신한다.
3. 증권사 실측, 계좌 대조, WebSocket 장중 수신, 주문 실증은 별도 사용자 환경·승인이 필요하며 소프트웨어 검사로 승격하지 않는다.

## 재개 명령

```powershell
.venv-rest\Scripts\python.exe -m pytest -q --tb=short
.venv-rest\Scripts\python.exe tools\verify_rest_migration.py
node --test cloud/worker.test.mjs web/board/*.test.js
npm run build
```

마지막 확인에서 verifier는 통과했다. 문서 전수 정리와 CI 원격 실행은 아직 완료되지 않았으므로 완료 상태로 표시하지 않는다.
