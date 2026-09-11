# TASK-024 IMPLEMENTATION

## Changed files

- `universe_manager.py`
  - 선택적인 external candidate 경로와 provider를 추가했다.
  - 전략별 source universe에 `external`을 추가하고 전체 전략 universe 병합에 포함했다.
  - 검증된 후보를 `strategy_tag`와 일치하는 전략에만 배치한다.
  - 만료·누락·손상·알 수 없는 전략 태그가 발생하면 external source만 비운다.
- `tests/test_task024_external_universe.py`
  - 전략별 격리, source 병합, 만료 reload, 누락·손상 파일, 알 수 없는 전략 태그를 검증한다.
  - external 실패 후 snapshot·condition과 보유종목·열린 주문 라우팅이 유지되는지 검증한다.
- `docs/agent-handoff/TASK-024-SPEC.md`
  - external universe 통합 범위와 안전 계약을 기록했다.

## Result

- `UniverseManager`는 snapshot, condition, external 세 source를 독립적으로 관리한다.
- 같은 종목을 서로 다른 전략 태그로 배치할 수 있으며 source별 조회와 병합 조회가 일관된다.
- external reload 실패는 이전 external 후보를 남기지 않고 다른 source에는 영향을 주지 않는다.
- external 경로는 선택 사항이며 기존 생성자는 동작을 유지한다.

## Safety

- `main_live.py`, `engine.py`, 전략, 주문, broker transport 및 `.env`를 변경하지 않았다.
- live 시작 흐름은 external 파일을 아직 읽지 않는다.
- 테스트는 temporary JSON과 in-memory universe만 사용했으며 외부 시스템을 호출하지 않았다.
