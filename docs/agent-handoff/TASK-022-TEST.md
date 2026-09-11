# TASK-022 TEST

## PowerShell command validation

README의 기본 예제와 같은 구조의 명령을 PowerShell parser로 검사했다.

```text
COMMAND_PARSE_OK
RUNNER_FOUND=C:\workspace\CherryPulse-KR-01\scripts\run-task.ps1
```

## Path validation

잘못된 문자열과 숨은 carriage-return 경로가 남지 않았는지 확인하고 정상 경로 세 곳을 찾았다.

```text
21:.\scripts\run-task.ps1 `
33:.\scripts\run-task.ps1 `
50:.\scripts\run-task.ps1 -TaskId TASK-001 -Goal "..."
```

## Whitespace validation

```text
git diff --check -- docs/agent-handoff/README.md
(no output)

DOC_CONTROL_AND_WHITESPACE_OK
```

untracked handoff 문서를 포함한 다섯 문서는 별도 검사로 trailing whitespace와 bare carriage return이 없음을 확인했다.

Python 및 PowerShell source는 변경하지 않았으므로 pytest와 runner 실행은 생략했다.

## Safety observations

- 검증은 parser와 파일 경로 조회만 수행했다.
- 자동 publish, Git 원격 쓰기, Kiwoom 연결, 계좌 조회 및 주문은 실행하지 않았다.
