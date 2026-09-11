# TASK-022 IMPLEMENTATION

## Changed files

- `docs/agent-handoff/README.md`
  - 손상된 runner 경로 두 곳을 `.\scripts\run-task.ps1`로 복구했다.
  - `cmd.exe` 프롬프트에서 PowerShell로 전환하는 절차를 추가했다.
  - 저장소 이동과 runner 실행을 하나의 복사 가능한 코드 블록으로 정리했다.
  - `Task ID:`, `Read:`, `BLOCKED`, 파일 경로 같은 실행 결과 문구를 명령으로 붙여 넣지 않도록 안내했다.
- `docs/agent-handoff/TASK-022-SPEC.md`
  - Windows runner 실행 안내의 범위와 검증 기준을 기록했다.

## Result

- 기본 실행 예제가 실제 repository의 runner 경로와 일치한다.
- 사용자는 `PS` 프롬프트를 확인한 후 코드 블록 안의 명령만 복사하면 된다.
- publish 옵션은 기존과 같이 reviewer 검토가 끝난 경우에만 별도로 사용하도록 유지했다.

## Safety

- 문서 외 파일은 변경하지 않았다.
- runner를 실행하지 않았으며 commit, push, PR 생성도 수행하지 않았다.
- `.env`, broker transport, live trading 설정, 계좌 및 주문 경로를 변경하거나 실행하지 않았다.
