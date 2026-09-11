# Agent handoff pipeline

이 디렉터리는 ChatGPT가 설계한 작업을 OpenCode 에이전트들이 순서대로 넘겨받는 공간이다.

## 역할

1. **analyzer**: 저장소를 조사하고 `TASK-ID-SPEC.md`를 작성한다.
2. **implementer**: SPEC만 계약으로 보고 코드를 수정하고 `TASK-ID-IMPLEMENTATION.md`를 작성한다.
3. **tester**: 코드를 수정하지 않고 테스트 증거를 `TASK-ID-TEST.md`에 기록한다.
4. **reviewer**: scope manifest의 exact 경로와 테스트를 독립 검토하고 `TASK-ID-REVIEW.md`에 PASS/CHANGES_REQUESTED/BLOCKED를 기록한다.

## 실행

runner는 Windows PowerShell 또는 PowerShell 7(`pwsh`)에서 실행한다. 프롬프트가
`C:\workspace\CherryPulse-KR-01>`처럼 `PS` 없이 표시되면 `cmd.exe`이므로 먼저
`powershell` 또는 `pwsh`를 입력한다. PowerShell 프롬프트가 표시되면 아래 코드
블록 안의 명령만 복사한다.

```powershell
Set-Location C:\workspace\CherryPulse-KR-01
.\scripts\run-task.ps1 `
  -TaskId TASK-001 `
  -Goal "손절을 전략·뉴스·일봉 캐시·시간 제한에서 분리하고 실패 경로 테스트를 추가"
```

실행 결과에 표시되는 `Task ID:`, `Read:`, `BLOCKED`, 파일 경로 같은 설명 문구는
다음 명령이 아니므로 터미널에 붙여 넣지 않는다. 다음 작업은 새 `TaskId`와 `Goal`로
위 runner 명령을 다시 실행한다.

검토가 끝난 뒤에만 브랜치 push와 PR 생성까지 자동화하려면:

```powershell
.\scripts\run-task.ps1 `
  -TaskId TASK-001 `
  -Goal "..." `
  -AutoPublish `
  -CreatePullRequest
```

첫 실행은 `-AutoPublish` 없이 smoke test를 권장한다. `main` 직접 실행, `.env`, 브로커 전송 파일, live trading 활성화는 안전검사에서 차단한다.

## Herdr 사용

Herdr는 작업 세션과 pane을 관리한다. 공식 문서에 맞게 Herdr workspace/pane 안에서 위 runner를 실행하면 된다.

```powershell
herdr --version
herdr workspace create --cwd C:\path\to\CherryPulse-KR-01 --label CherryPulse
# 생성된 Herdr pane에서:
.\scripts\run-task.ps1 -TaskId TASK-001 -Goal "..."
```

저장소에는 확인되지 않은 `herdr.yaml` 문법을 넣지 않았다. 먼저 위 runner를 안정화한 뒤, 설치된 Herdr 버전의 `herdr --help`와 실제 pane 출력에 맞춰 native pane orchestration을 추가한다.

## 산출물 규칙

- `*-SPEC.md`: 설계 계약
- `*-IMPLEMENTATION.md`: 변경 파일과 구현 결과
- `*-TEST.md`: 실제 실행 명령과 결과
- `*-REVIEW.md`: 독립 검토 판정 (scope manifest의 `reviewPaths`만 판정 근거)
- `*-SCOPE-MANIFEST.md`: 현재 TASK의 exact review 경로 계약
- `*-BASELINE.json`: 실행 시작 상태를 기록하는 로컬 metadata (`.gitignore` 대상)
- `*.log`: 각 단계의 OpenCode 원본 로컬 로그 (`.gitignore` 대상)

handoff 파일과 로그에는 비밀키, 토큰, 계좌번호를 기록하지 않는다.

## TASK baseline/scope 계약

runner는 첫 stage 전에 `TASK-ID-BASELINE.json`에 HEAD SHA, porcelain status 원문,
baseline path/hash와 UTC 시각을 원자적으로 기록한다. 이후
`TASK-ID-SCOPE-MANIFEST.md`의 `reviewPaths`만 현재 TASK의 판정 근거다.
baseline 이전 변경, 이전 TASK handoff, 단계 로그는 `excludedPaths`이며 되돌리거나
삭제하지 않는다. reviewer와 diff-check는 exact `reviewPaths` pathspec만 사용하고,
untracked source/test도 반드시 명시적으로 읽는다. metadata가 없거나 stale이면
publish하지 않는다. baseline JSON과 단계 로그는 로컬 실행 증거이므로 Git 상태에
노출하지 않고, SPEC·SCOPE-MANIFEST·IMPLEMENTATION·TEST·REVIEW 문서는 계속 추적한다.
새 `.env*`, broker transport, live enablement는 항상 차단한다.
