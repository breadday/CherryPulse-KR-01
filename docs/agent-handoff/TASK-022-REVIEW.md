# PASS

Evidence:

- README의 두 손상 경로가 실제 runner 위치인 `.\scripts\run-task.ps1`로 복구됐다.
- 문서는 `cmd.exe` 프롬프트를 식별하고 PowerShell로 전환하는 방법을 명시한다.
- 복사 대상은 코드 블록 안의 명령으로 제한되며 `Task ID:`, `Read:`, `BLOCKED`, 파일 경로는 실행 결과 문구로 구분된다.
- PowerShell parser가 기본 명령을 오류 없이 해석했고 `Get-Command`가 repository의 runner를 찾았다.
- 잘못된 경로와 숨은 carriage-return 경로는 남지 않았으며 문서 whitespace 검사도 통과했다.
- source, test, runner, `.env`, broker transport, live enablement 및 거래 로직은 변경하지 않았다.

Verdict: TASK-022의 문서 실행 안내 개선은 PASS다.
