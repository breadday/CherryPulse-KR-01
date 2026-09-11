# TASK-010 구현 명세 — TASK 범위 추적 및 reviewer 입력 격리

상태: `IMPLEMENTATION_CONTRACT` (아직 구현되지 않은 계약)
목표: 거래 로직을 건드리지 않고 자동개발 검토 경계를 정확히 분리한다.

## 1. 현재 동작과 확인 근거

현재 HEAD의 runner는 `scripts/run-task.ps1`에서 baseline을 단순 Markdown/path 목록으로 만들고, 전체 untracked를 `git add --intent-to-add`하여 reviewer에 노출한다. 또한 reviewer prompt가 `git diff main`과 전체 working-tree status를 판정 근거로 사용할 수 있다. `scripts/safety-check.ps1`도 branch-wide diff를 검사하며 baseline별 범위를 알지 못한다.

현재 working tree에는 TASK-001~009 handoff/log, TASK-010 산출물, 그리고 `engine.py`, `main_live.py`, `core/*` 등의 pre-existing 변경이 함께 있다(`git status --short --branch` 확인). 이 파일들을 되돌리거나 TASK-010 변경으로 재분류하면 안 된다.

근거 위치:

- `scripts/run-task.ps1`: `Expose-UntrackedForReview`, `Write-ScopeManifest`, baseline 초기화, reviewer prompt, publish 직전 흐름
- `scripts/safety-check.ps1`: `Changed-Paths` 및 branch-wide live/whitespace 검사
- `.opencode/agents/reviewer.md`: 전체 diff/status 사용 지시와 scope 검토 지시
- `docs/agent-handoff/README.md`: 현재 handoff 산출물 규칙

## 2. 변경 범위와 심볼별 계약

### A. `scripts/run-task.ps1`

대상: `Get-StatusPath`, `Expose-UntrackedForReview`, `Write-ScopeManifest`, baseline 초기화, `Run-Stage`, reviewer prompt 및 publish 전 재검증.

1. 첫 stage와 safety check 전에 다음을 한 번 수집한다.
   - `baselineHead = git rev-parse HEAD`의 전체 SHA
   - `baselineStatus = git status --porcelain=v1 --untracked-files=all` 원문 배열
   - staged/unstaged/untracked의 repository-relative path 집합과 파일 hash
   - branch 및 UTC timestamp
2. `docs/agent-handoff/$TaskId-BASELINE.json`에 UTF-8 JSON을 원자적으로 기록한다. metadata에는 파일 내용, `.env` 값, token, 계좌번호를 기록하지 않는다. 기록 실패 시 어떤 stage도 실행하지 않는다.
3. path 비교는 `/` canonical form으로 하고 rename의 old/new 양쪽을 고려한다.
4. baseline 이후의 committed diff, staged/unstaged diff, 전체 untracked를 합쳐 후보를 계산한다. baseline path는 `excludedPaths`로 남기되 reviewer/diff-check에서 제외하고, 기존 working-tree 파일은 변경하거나 삭제하지 않는다.
5. `reviewPaths`에는 baseline 이후 새로 변경된 source/test와 현재 TASK의 handoff 문서만 넣는다. manifest는 `TASK-010-SCOPE-MANIFEST.md` 단일 형식으로 관리하고, `TASK-010-BASELINE.json`은 baseline 정보로만 관리한다. 이전 TASK handoff와 모든 `docs/agent-handoff/*.log`는 제외한다.
6. `.env*`, `broker/kiwoom_broker.py`, `broker/kiwoom.py` 또는 기타 broker transport 신규 변경은 제외가 아니라 즉시 실패다. source/test/current-task handoff 이외의 신규 path도 allowlist 위반으로 실패시킨다.
7. `Expose-UntrackedForReview`는 전체 untracked를 index에 추가하지 않는다. exact `reviewPaths`를 reviewer prompt와 manifest에 전달하고, 특히 untracked test는 파일 목록과 실제 content를 reviewer가 읽을 수 있게 한다.
8. reviewer prompt는 baseline metadata와 exact `reviewPaths`를 제공한다. 현재 TASK 판정과 `git diff`/`git diff --check`는 이 pathspec만 사용하며, `git diff main`, 전체 status, 이전 handoff/log는 참고 또는 판정 근거로 사용하지 못하게 한다.
9. reviewer 후 scope를 재계산한다. 새 source/test/current-task handoff, 누락/변경된 manifest, stale baseline이 있으면 PASS/publish하지 않는다.

### B. `scripts/safety-check.ps1`

대상: parameter block, `Status-Paths`, `Load-Baseline`, `Changed-Paths`, live enablement 검사, post validation.

- `-BaselinePath`와 `-ScopePath`를 지원하고 runner가 항상 전달한다. 누락/손상/필수 필드 불일치 metadata는 throw/BLOCK한다.
- forbidden/live 검사는 baseline 이후 신규 path에 적용하되, 새 `.env*`, broker transport, `RUN_MODE=live`, `LIVE_TRADING=True` 활성화는 항상 실패시킨다. baseline에만 있던 문자열은 false positive가 아니어야 한다.
- post `git diff --check`는 `reviewPaths` 배열 pathspec에만 실행한다. staged와 unstaged를 모두 검사하고 log, 이전 TASK handoff, baseline path는 검사하지 않는다.
- pathspec은 배열 인자로 전달해 공백/한글/특수문자와 shell injection을 안전하게 처리한다.
- 출력에는 baseline SHA, review path 수, excluded path 수, untracked test 수만 요약하고 secret은 출력하지 않는다.

### C. `.opencode/agents/reviewer.md` 및 `docs/agent-handoff/README.md`

- reviewer는 manifest와 baseline을 먼저 읽고 missing/unreadable/empty/stale이면 정확히 `BLOCKED`를 기록한다.
- exact `reviewPaths`만 현재 TASK의 source/test/handoff 판정 및 diff-check 대상으로 삼는다. 모든 log와 이전 TASK 산출물은 scope 밖이다.
- reviewPaths의 untracked source/test는 내용까지 읽는다. 누락하면 PASS 금지(`BLOCKED` 또는 `CHANGES_REQUESTED`).
- 기존 거래 안전성 검토(손절 우선, stale/reconnect, order ID, live/broker/secret 차단)는 유지하되 거래 코드 자체는 수정·실행하지 않는다.
- reviewer는 source를 수정하지 않고 지정 handoff에 verdict 하나만 기록한다.

### D. 테스트

`tests/test_task_scope_contract.py`를 확장하거나 `tests/test_task_scope_*.py`를 추가한다. temporary Git repository와 stage/reviewer stub을 사용하며 키움/COM, `main_live.py`, 주문 제출을 호출하지 않는다. 기존 거래/risk 테스트의 동작과 production trading code는 변경하지 않는다.

## 3. 불변조건 및 안전 제약

1. baseline HEAD/status는 첫 stage 전 기록하고 덮어쓰지 않는다.
2. baseline pre-existing 변경은 보존하며 current TASK scope/diff-check에서 제외한다.
3. baseline 이후 허용된 source/test는 모두 reviewer에 전달한다. untracked test content 없이 PASS할 수 없다.
4. `docs/agent-handoff/*.log`와 이전 TASK handoff는 `git diff` 및 `git diff --check` 대상이 아니다.
5. current TASK의 source·test·handoff 문서만 검증한다. log의 trailing whitespace는 실패 사유가 아니며 current reviewPath의 whitespace는 실패다.
6. `.env`, broker transport, live trading 활성화 변경은 발견 즉시 차단한다.
7. protected branch/detached HEAD, metadata stale, reviewer 후 scope 변경이면 publish하지 않는다.
8. baseline 이전 파일을 되돌리거나 삭제하지 않고, runner는 거래 로직을 수정하거나 live/broker 연결을 실행하지 않는다.

## 4. Acceptance tests

### 정상 경로

- pre-existing staged/unstaged/untracked source/test, TASK-001~009 handoff/log가 있는 temporary repo에서 baseline SHA/status/hash가 보존되고 모두 `excludedPaths`가 되는지 확인한다.
- baseline 이후 tracked/staged/unstaged source와 새 **untracked** `tests/test_scope.py`, TASK-010 handoff를 만들면 exact `reviewPaths`, reviewer prompt, manifest에 모두 나타나고 test content도 전달되는지 확인한다.
- TASK 중간 commit이 생겨도 baseline HEAD 기준으로 새 path가 누락되지 않는지 확인한다.
- 이전 log에 trailing whitespace가 있어도 diff-check가 통과하고, 현재 TASK source/test의 trailing whitespace는 실패하는지 확인한다.

### 실패 경로

- baseline JSON 누락, malformed, 필수 필드 누락, scope stale이면 stage/post/publish가 중단되고 `BLOCKED`/throw인지 확인한다.
- reviewer 후 새 source/test/handoff가 생기거나 manifest와 actual scope가 달라지면 publish하지 않는지 확인한다.
- 새 `.env`, `.env.local`, broker transport 파일 또는 live enablement diff가 pre/post에서 차단되고 reviewer scope에 조용히 숨겨지지 않는지 확인한다.
- reviewer stub이 untracked test를 읽지 않거나 이전 TASK 파일/log를 판정 근거로 사용하면 non-PASS인지 확인한다.
- detached HEAD와 `main`/`master`에서 첫 stage 전에 중단하는지 확인한다.

### 검증 명령

```powershell
python -m pytest -q
python -m pytest -q tests/test_task_scope_contract.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\safety-check.ps1 -Mode pre -BaselinePath <fixture-baseline> -ScopePath <fixture-scope>
git diff --check -- <reviewPaths>
```

구현 보고서에는 실제 명령/결과, baseline SHA/status, review/excluded 수, untracked test 목록과 각 실패 경로 결과를 기록한다. 실제 주문 경로는 실행하지 않는다.

## 5. 롤백 고려사항

- 변경/롤백 범위는 `scripts/run-task.ps1`, `scripts/safety-check.ps1`, `.opencode/agents/reviewer.md`, `docs/agent-handoff/README.md`, TASK-010 scope 테스트와 문서로 한정한다.
- `engine.py`, `main_live.py`, `broker/*`, `core/*`, 전략, SQLite는 이 TASK에서 수정하지 않으며 pre-existing 변경도 보존한다.
- 자동 publish 전 롤백할 경우 runner/safety/reviewer와 baseline/scope metadata의 버전을 함께 되돌린다. 구버전 runner만 복구하면 이전 log와 untracked test가 전체 diff에 섞일 수 있다.
- baseline metadata 손상 시 전체 diff를 대체 근거로 사용하지 말고 `BLOCKED` 후 안전한 재실행/재생성 절차를 사용한다.
- secret/broker/live 변경은 rollback으로 숨기지 말고 격리하여 수동 보안 검토한다.
