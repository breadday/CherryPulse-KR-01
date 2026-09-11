# TASK-023 SPEC

## Goal

외부 종목선정 시스템이 생성한 JSON 후보를 거래 코드와 분리된 순수 provider로 읽고, 유효한 미만료 후보만 신규 진입 입력으로 제공하는 계약을 만든다.

## Scope

- `selectors.external_candidate_provider.ExternalCandidateProvider`를 추가한다.
- JSON 최상위 스키마는 `schema_version: 1`과 `candidates` 배열로 제한한다.
- 후보 필드는 `symbol`, `name`, `selection_date`, `strategy_tag`, `intended_holding_period`, `source`, `expires_at`을 필수로 한다.
- 종목 코드는 6자리 숫자, 선택일은 ISO date, 만료 시각은 timezone이 포함된 ISO datetime이어야 한다.
- 같은 `symbol + strategy_tag`가 중복되거나 후보 하나라도 잘못되면 파일 전체를 거부한다.
- `expires_at <= as_of` 후보는 결과에서 제외하며 한국 시장 날짜보다 미래인 선택일은 거부한다.

## Safety constraints

- provider와 단위 테스트만 추가한다.
- `UniverseManager`, `engine.py`, `main_live.py`, 전략, 주문, broker transport, `.env`, live trading 설정을 변경하지 않는다.
- 외부 네트워크, SQLite, Kiwoom COM, 계좌 및 주문 API를 호출하지 않는다.

## Acceptance criteria

- 정상 파일은 필드가 정규화된 불변 후보 객체를 반환한다.
- 만료 경계와 만료된 후보는 신규 진입 결과에서 제외된다.
- 누락 파일, 잘못된 JSON/스키마/필드/날짜/종목 코드/중복은 명시적 예외를 발생시킨다.
- focused test와 전체 Python 3.10 테스트가 통과한다.
- 변경 파일에 문법 및 whitespace 오류가 없다.
