# 자동 개발 실행 가이드

이 저장소의 자동 개발은 ChatGPT가 매번 코드를 작성하는 방식이 아니다. ChatGPT는 작업 목표와 검토 기준을 만들고, 로컬의 Herdr/OpenCode가 구현 파이프라인을 실행한다.

## 구조

- Herdr: workspace와 pane을 유지하는 실행 감독자
- OpenCode: analyzer → implementer → tester → reviewer 실행자
- handoff: 각 단계의 파일 기반 계약
- safety-check: 보호 브랜치·비밀값·실거래 활성화·브로커 파일 변경 차단

## 최초 1회

Windows PowerShell에서 프로젝트를 내려받은 뒤 자동화 브랜치를 체크아웃한다.

```powershell
git fetch origin
git checkout automation/opencode-herdr-pipeline
```

다음 명령이 설치되어 있어야 한다.

```powershell
git --version
herdr --version
opencode --version
python --version
```

이 저장소의 `opencode.jsonc`와 `.opencode/agents/` 설정은 프로젝트 루트에서 실행할 때 적용된다.

## 실행

Herdr workspace를 만든 뒤 그 pane에서 runner를 한 번 실행한다.

```powershell
herdr workspace create --cwd C:\path\to\CherryPulse-KR-01 --label CherryPulse
.\scripts\run-task.ps1 `
  -TaskId TASK-001 `
  -Goal "TASK-001-REQUEST.md의 RiskGuard 분리와 손절 실패경로를 구현"
```

실행 결과는 다음에 남는다.

```
docs/agent-handoff/TASK-001-SPEC.md
docs/agent-handoff/TASK-001-IMPLEMENTATION.md
docs/agent-handoff/TASK-001-TEST.md
docs/agent-handoff/TASK-001-REVIEW.md
docs/agent-handoff/TASK-001-*.log
```

## publish 규칙

첫 실행은 자동 push 없이 확인한다. reviewer가 PASS이고 diff를 사람이 확인한 뒤에만 다음 옵션을 사용한다.

```powershell
.\scripts\run-task.ps1 `
  -TaskId TASK-001 `
  -Goal "TASK-001-REQUEST.md의 RiskGuard 분리와 손절 실패경로를 구현" `
  -AutoPublish `
  -CreatePullRequest
```

이 옵션은 main에 merge하지 않고 자동화 브랜치 push와 PR 생성까지만 한다. merge는 GitHub 보호규칙과 사람 승인을 거친다.

## 토큰 절약 원칙

- ChatGPT는 같은 코드를 반복해서 읽지 않고 SPEC과 acceptance test를 만든다.
- OpenCode에는 단계별로 필요한 파일과 역할을 제한한다.
- analyzer가 만든 SPEC을 implementer가 재사용한다.
- tester/reviewer는 생산 코드를 수정하지 않는다.
- 실패하면 전체 대화를 다시 보내지 않고 해당 handoff 파일과 로그만 재실행한다.

## 현재 한계

Herdr의 설치 버전별 CLI 옵션이 다를 수 있으므로 저장소는 확인되지 않은 `herdr.yaml` 문법을 전제하지 않는다. Herdr가 runner를 pane에서 실행하는 것까지 먼저 검증하고, 그 뒤 필요하면 설치된 버전에 맞는 native pane orchestration을 추가한다.
