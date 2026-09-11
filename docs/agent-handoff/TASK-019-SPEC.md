# TASK-019 SPEC

## Goal

runner의 로컬 evidence 파일이 다음 TASK의 working tree와 scope 계산을 오염시키지 않도록 Git ignore 계약을 명시한다.

## Scope

- `docs/agent-handoff/*.log`를 Git ignore 대상으로 지정한다.
- `docs/agent-handoff/TASK-*-BASELINE.json`을 Git ignore 대상으로 지정한다.
- handoff README에 local evidence와 추적 문서의 구분을 기록한다.
- 기존 파일은 삭제하거나 이동하지 않는다.

## Safety constraints

- runner와 safety-check 동작을 변경하지 않는다.
- SPEC, SCOPE-MANIFEST, IMPLEMENTATION, TEST, REVIEW 문서는 ignore하지 않는다.
- production, 거래, broker, `.env`, live 설정을 변경하거나 실행하지 않는다.

## Acceptance criteria

- 기존 handoff log와 baseline JSON에 `git check-ignore`가 성공한다.
- TASK handoff Markdown 문서는 `git check-ignore` 대상이 아니다.
- `git status --untracked-files=all`에서 log와 baseline JSON이 사라진다.
- 기존 로컬 evidence 파일은 그대로 존재한다.
