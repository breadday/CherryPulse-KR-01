# PASS

Evidence:

- TASK-012 전용 binding failure 테스트 3개가 통과했다.
- missing, ambiguous, existing broker identity conflict 경로 모두 자동 cancel/re-submit 없이 fail-closed로 종료된다.
- rollback 후 신규 local order와 양방향 mapping, risk event map, `sell_in_progress`가 제출 전 상태로 복원된다.
- durable risk event는 삭제되지 않고 `MANUAL_INTERVENTION_REQUIRED`로 유지된다.
- broker transport, `.env`, live enablement, 실제 주문·체결 경로는 실행·변경하지 않았다.
