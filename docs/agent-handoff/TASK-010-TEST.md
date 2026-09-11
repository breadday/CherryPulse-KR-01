# TASK-010 테스트 결과

## 실행 결과

- 명령: `python -m pytest -q tests/test_task_scope_contract.py tests/test_task_runner_e2e.py`
  - 결과: PASS — `25 passed in 115.97s`
- 명령: `python -m pytest -q`
  - 결과: PASS — `41 passed in 117.40s`
- 명령: PowerShell parser로 `scripts/run-task.ps1`, `scripts/safety-check.ps1` 파싱
  - 결과: PASS — `PARSER_OK`
- 명령: `scripts/safety-check.ps1 -Mode post`와 manifest의 10개 review path에 대한 `git diff --check`
  - 결과: PASS — `reviewPaths=10 excludedPaths=8 untrackedTests=2`; LF→CRLF 변환 경고만 출력됨.

## 테스트된 범위

- 임시 Git 저장소의 baseline SHA/status/hash 보존
- staged/unstaged/untracked 범위 계산 및 untracked 테스트 전달
- stale metadata/scope, reviewer 후 scope 변경
- `.env*`, broker transport, live enablement 차단
- protected branch 및 detached HEAD 차단
- baseline 제외 경로와 이전 handoff/log 격리
- reviewer verdict의 입력 범위 제외 및 intent-to-add 테스트의 working-tree content 전달
- intent-to-add source의 live enablement 및 intent-to-add test의 trailing whitespace 차단
- 테스트 파일의 실제 live 설정 할당 차단과 fixture 문자열 오탐 방지
- 실제 runner stage 순서, PowerShell 5.1/7 manifest 생성, baseline Git hash, manifest 변조 및 reviewer 산출물 누락 차단
- baseline 이후 commit된 파일 추적과 missing/malformed baseline 차단
- 외부 safety-check nonzero 종료 전파, 독립 review/excluded allowlist, untrackedTests 누락 차단
- AutoPublish의 exact task path staging 및 기존 baseline index 변경 격리

## 실행하지 않은 범위

- 실제 OpenCode reviewer stage/publish
- 실제 주문·체결·Kiwoom/COM 경로
