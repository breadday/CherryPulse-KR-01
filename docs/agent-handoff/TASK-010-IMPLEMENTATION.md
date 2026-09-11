# TASK-010 구현 보고서

## 변경 내용

- `.opencode/agents/reviewer.md`: 기존 JSON/branch-wide review 지시를 제거하고 현재 working directory의 baseline JSON과 Markdown scope manifest를 직접 읽도록 수정했다. `git rev-parse`, metadata 확인용 Python, post safety-check에 필요한 읽기 전용 권한을 추가했다. intent-to-add(` A`) 파일을 staged content로 오인하지 않고 working-tree content로 직접 검토하도록 명시했다.
- `scripts/run-task.ps1`: 실행 시작 시 HEAD, porcelain status, baseline path/hash를 `TASK-010-BASELINE.json`에 기록하고, baseline 이후의 허용된 source/test/current TASK handoff만 `TASK-010-SCOPE-MANIFEST.md`의 `reviewPaths`에 포함하도록 수정했다. baseline JSON, 이전 TASK handoff, 로그와 reviewer가 작성할 현재 TASK review verdict는 검토 입력에서 제외한다. TASK ID를 정규식에 고정하지 않고 실행 인자를 사용하며, 실제 untracked 및 intent-to-add 테스트만 `untrackedTests`에 기록한다. PowerShell 내장 `Get-FileHash`와 충돌하지 않는 Git hash helper를 사용하고, PowerShell 5.1/7 모두에서 manifest 경로 배열과 BOM 없는 UTF-8 metadata를 동일하게 기록한다. 모든 외부 safety-check 종료 코드를 확인하고, reviewer 전후 manifest hash와 정확히 하나의 verdict를 검증한 뒤 scope를 재생성해 post safety를 다시 실행한다. AutoPublish는 exact task publish paths만 stage하고 `git commit --only`로 baseline의 기존 index 변경을 보존한다.
- `scripts/safety-check.ps1`: Markdown scope manifest를 읽고 baseline 이후 실제 변경 경로와 선언된 scope를 비교한다. baseline metadata 경로를 repository-relative로 정규화하고 단일 경로 배열이 문자열로 합쳐지지 않게 수집한다. runner와 독립적으로 review/excluded allowlist, 섹션 중복, untrackedTests 누락·허위 항목을 검사하고 모든 신규 `broker/` 및 `.env*` 경로를 차단한다. `git add -N` 경로의 전체 content에서 live enablement와 trailing whitespace를 검사하며, 테스트 경로도 실제 설정 할당만 탐지한다.
- `docs/agent-handoff/README.md`: baseline과 Markdown scope manifest의 운영 규칙을 문서화했다.
- `tests/test_task_scope_contract.py`: 실제 임시 Git repository에서 staged/unstaged/untracked 변경, baseline 제외, untracked test 전달, stale scope, forbidden `.env`/broker, live enablement, 테스트 경로의 실제 live 할당, intent-to-add live/whitespace 차단, protected/detached branch, reviewer 이후 scope 변경을 검증한다.
- `tests/test_task_runner_e2e.py`: 임시 Git 저장소와 로컬 OpenCode stub으로 실제 runner의 analyzer→implementer→tester→reviewer 흐름을 실행한다. baseline 선기록, exact scope 전달, 이전 log 제외, manifest 변조, reviewer 산출물 누락, TASK 중간 commit, missing/malformed baseline을 검증한다.

## 검증

- `python -m pytest -q tests/test_task_scope_contract.py tests/test_task_runner_e2e.py`: 통과, `25 passed in 115.97s`
- `python -m pytest -q`: 통과, `41 passed in 117.40s`
- PowerShell parser 검사: 통과, `PARSER_OK`
- `tests/test_task_runner_e2e.py`: 통과, `6 passed in 47.12s`
- PowerShell parser: 통과, `PARSER_OK`
- 최종 post safety: 통과, `reviewPaths=10 excludedPaths=8 untrackedTests=2`
- manifest의 10개 review path에 대한 `git diff --check`: 통과

## 안전성

거래 로직, broker transport, `main_live.py`, 주문 제출 경로는 수정하거나 실행하지 않았다. 커밋, push, merge, AutoPublish도 실행하지 않았다.

## 남은 검증

실제 OpenCode reviewer를 반복 실행해 발견된 scope/live/fail-closed 문제를 반영했다. 최종 reviewer 재검토와 publish는 아직 실행하지 않았다. 실제 주문·체결·Kiwoom/COM 경로는 실행하지 않았다.
