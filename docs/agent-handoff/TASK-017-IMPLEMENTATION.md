# TASK-017 IMPLEMENTATION

## Changed files

- `tests/test_task017_universe_isolation.py`
  - 실제 전략 이름과 source 설정으로 `UniverseManager`를 구성한다.
  - 태그된 snapshot 후보의 전략별 분리와 shared 후보를 검증한다.
  - condition 제거가 snapshot 소속을 지우지 않는지 검증한다.
  - snapshot 교체가 stale snapshot만 제거하고 condition 소속을 유지하는지 검증한다.
  - selector universe name 매핑과 보유·미체결 종목 라우팅을 검증한다.
- `docs/agent-handoff/TASK-017-SPEC.md`
  - 전략 유니버스 격리 계약과 안전 제약을 기록했다.

## Result

- 현재 `UniverseManager` 구현은 검증한 source·strategy 경계에서 정상 동작했다.
- production 변경은 필요하지 않았다.
- CI 전체 테스트 수는 73개에서 77개로 증가한다.

## Safety

- 전략 설정과 production 코드를 변경하지 않았다.
- 테스트는 메모리 내 유니버스만 사용하며 snapshot 파일을 읽거나 쓰지 않는다.
- Kiwoom, COM, 계좌, 주문 API 또는 live trading 경로를 실행하지 않았다.
