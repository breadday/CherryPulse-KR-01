# TASK-019 IMPLEMENTATION

## Changed files

- `.gitignore`
  - `docs/agent-handoff/*.log`를 local evidence로 ignore한다.
  - `docs/agent-handoff/TASK-*-BASELINE.json`을 local metadata로 ignore한다.
- `docs/agent-handoff/README.md`
  - baseline JSON과 stage log가 로컬 전용임을 명시했다.
  - SPEC, SCOPE-MANIFEST, IMPLEMENTATION, TEST, REVIEW가 추적 문서임을 명시했다.
- `docs/agent-handoff/TASK-019-SPEC.md`
  - working tree 오염 방지 계약을 기록했다.

## Result

- 기존 41개 stage log와 TASK-010 baseline JSON이 normal Git status에서 제외된다.
- 기존 evidence 파일은 삭제하거나 이동하지 않았다.
- TASK Markdown 문서는 계속 untracked/tracked 변경으로 표시된다.

## Safety

- runner, safety-check, production 코드와 거래 설정을 변경하지 않았다.
- `.env`, broker transport, live enablement, account, order path를 실행하지 않았다.
