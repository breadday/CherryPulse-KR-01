# AGENTS.md

이 프로젝트에서 AI 에이전트는 아래 문서를 먼저 읽고 작업한다.

1. `docs/harness/DESIGN_PRINCIPLES.md`
2. `docs/harness/FILE_RESPONSIBILITY.md`
3. `docs/harness/CHANGE_CHECKLIST.md`
4. `docs/harness/AI_WORKFLOW.md`

## 핵심 원칙

- 현재 기본 방향은 일봉 후보 기반 스윙 매매다.
- `RUN_MODE=live`와 키움 모의투자 계좌를 사용해 실계좌 실매매와 같은 흐름으로 검증한다.
- 계좌가 실계좌로 바뀌면 실제 주문이 발생할 수 있으므로 주문 경로는 항상 엄격하게 다룬다.
- 조건검색과 틱 단타는 기본 비활성이다.
- 전략별 후보와 성과는 독립적으로 관리한다.
- 코드 변경 후 문법 검사와 관련 검증을 실행한다.
