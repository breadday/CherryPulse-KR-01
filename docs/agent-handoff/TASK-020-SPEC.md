# TASK-020 SPEC

## Goal

로컬 evidence ignore 계약이 적용된 실제 임시 Git 저장소에서 TASK runner의 baseline, scope, tester, reviewer 흐름이 정상 동작하는지 E2E로 검증한다.

## Scope

- runner E2E fixture에 저장소 `.gitignore`를 포함한다.
- 이전 TASK log가 baseline path로 수집되지 않는지 검증한다.
- 현재 TASK baseline JSON과 stage log가 normal Git status에 나타나지 않는지 검증한다.
- ignored evidence 파일이 실제로 생성·보존되는지 검증한다.
- SCOPE-MANIFEST, REVIEW, untracked test는 계속 Git/reviewer에 전달되는지 검증한다.

## Safety constraints

- production runner와 safety-check는 변경하지 않는다.
- 모든 runner 실행은 임시 Git 저장소와 `opencode.cmd` stub에서 수행한다.
- commit은 임시 fixture 저장소 안에서만 생성한다.
- broker, `.env`, live trading, 계좌, 주문 API를 실행하지 않는다.

## Acceptance criteria

- success E2E가 `TASK_COMPLETE`로 끝난다.
- baseline metadata에 이전 ignored log가 포함되지 않는다.
- baseline JSON과 모든 stage log는 파일로 존재하지만 normal Git status에는 없다.
- manifest와 review는 Git status에 나타난다.
- reviewer stub이 untracked test 내용을 읽고 PASS를 기록한다.
- 전체 pytest가 통과한다.
