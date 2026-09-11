# TASK-020 IMPLEMENTATION

## Changed files

- `tests/test_task_runner_e2e.py`
  - 임시 runner 저장소에 실제 `.gitignore`를 복사한다.
  - 이전 TASK log가 baseline paths에서 제외되는지 검증한다.
  - 현재 TASK baseline JSON과 네 단계 log가 생성되지만 normal Git status에는 없는지 검증한다.
  - SCOPE-MANIFEST와 REVIEW가 Git status에 남고 untracked test가 reviewer에게 전달되는 기존 검증을 유지한다.
- `docs/agent-handoff/TASK-020-SPEC.md`
  - ignored evidence 상태의 runner E2E 계약을 기록했다.

## Result

- TASK-019의 ignore 정책과 TASK-010 runner scope 정책이 실제 임시 Git 저장소에서 함께 동작한다.
- production runner와 safety-check 변경은 필요하지 않았다.
- 기존 success, tamper, missing review, unsafe change, committed-after-baseline, malformed baseline 시나리오가 모두 유지된다.

## Safety

- runner가 만드는 commit은 pytest 임시 저장소 안에서만 생성됐다.
- 실제 작업 브랜치에서 commit, push, PR 또는 publish를 실행하지 않았다.
- broker, `.env`, live trading, 계좌, 주문 API를 실행하지 않았다.
