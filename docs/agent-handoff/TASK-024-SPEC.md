# TASK-024 SPEC

## Goal

검증된 외부 후보를 `UniverseManager`의 독립 source로 수용하고, 전략 태그별 신규 진입 유니버스를 snapshot·조건검색과 섞이지 않게 관리한다.

## Scope

- `UniverseManager`에 선택적인 external candidate 경로와 provider를 추가한다.
- 전략별 source universe에 `external`을 추가하고 `strategy_tag`가 일치하는 전략에만 종목을 배치한다.
- 외부 파일의 누락·손상·미지원 전략 태그 또는 만료 시 external source를 비워 fail-closed 처리한다.
- external source를 다시 로드해도 snapshot·condition source는 유지한다.
- 보유종목과 열린 주문의 기존 라우팅 우선권을 유지한다.

## Safety constraints

- `main_live.py`, `engine.py`, 전략, 주문, broker transport, `.env`, live trading 설정을 변경하지 않는다.
- external provider를 live 시작 흐름에 연결하지 않는다.
- 테스트는 temporary JSON과 `UniverseManager`만 사용한다.
- Kiwoom COM, 계좌, 주문, 네트워크 및 SQLite를 호출하지 않는다.

## Acceptance criteria

- 같은 종목이 서로 다른 전략 태그로 들어올 수 있으며 각 전략 source에만 나타난다.
- external 후보는 기존 snapshot·condition 후보와 합쳐지되 source별 조회에서는 격리된다.
- 만료 또는 로드 오류 후 external 후보가 남지 않는다.
- 알 수 없는 전략 태그는 조용히 무시하지 않고 오류로 처리된다.
- 기존 보유종목·열린 주문 라우팅 및 TASK-017 테스트가 회귀하지 않는다.
- focused test와 전체 Python 3.10 테스트가 통과한다.
