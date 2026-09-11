# TASK-022 SPEC

## Goal

agent handoff runner의 Windows 실행 안내를 실제 PowerShell 명령과 일치시키고, `cmd.exe`에 에이전트 출력문을 붙여 넣어 발생하는 실행 오류를 예방한다.

## Scope

- runner 경로를 `.\scripts\run-task.ps1` 형식으로 수정한다.
- `cmd.exe`와 PowerShell 프롬프트를 구분하는 방법을 명시한다.
- 사용자가 복사할 명령과 실행 결과 설명문을 구분한다.
- 자동 publish 옵션은 기존처럼 검토 완료 후 사용하는 흐름을 유지한다.

## Safety constraints

- 문서만 변경한다.
- runner, source, test, `.env`, broker transport, live trading 설정을 변경하지 않는다.
- commit, push, PR 생성, 주문 및 Kiwoom 연결을 실행하지 않는다.

## Acceptance criteria

- README에 잘못된 `.scripts\run-task.ps1` 경로가 남지 않는다.
- 안내된 기본 명령이 PowerShell parser에서 오류 없이 해석된다.
- repository에서 runner 경로를 PowerShell이 찾을 수 있다.
- 변경 문서에 whitespace 오류가 없다.
