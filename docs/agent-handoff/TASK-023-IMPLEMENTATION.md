# TASK-023 IMPLEMENTATION

## Changed files

- `selectors/external_candidate_provider.py`
  - 불변 `ExternalCandidate` 모델과 `ExternalCandidateProvider`를 추가했다.
  - schema version, 필수 문자열, 6자리 종목 코드, ISO 선택일, timezone 포함 만료 시각을 검증한다.
  - UTF-8 BOM, UTC `Z`, offset datetime을 처리하고 만료 경계의 후보를 제외한다.
  - 한국 시장 날짜를 기준으로 미래 선택일을 차단한다.
  - 동일 `symbol + strategy_tag` 중복과 부분적으로 잘못된 문서를 전체 거부한다.
- `selectors/__init__.py`
  - 외부 후보 모델, provider, 예외를 package API로 노출했다.
- `tests/test_task023_external_candidate_provider.py`
  - 정상 정규화, 만료, KST 날짜 경계, 필드·문서 오류, 중복, 누락·손상 파일을 검증한다.
- `docs/agent-handoff/TASK-023-SPEC.md`
  - 외부 후보 JSON 계약과 안전 범위를 기록했다.

## Result

- 외부 후보 파일은 거래 엔진과 독립적으로 검증할 수 있다.
- 잘못된 후보를 조용히 건너뛰지 않아 일부만 유효한 문서가 신규 진입 입력으로 사용되지 않는다.
- provider는 아직 `UniverseManager` 또는 live 실행 흐름에 연결하지 않았다.

## Safety

- `engine.py`, `main_live.py`, 전략, 주문, broker transport 및 `.env`를 변경하지 않았다.
- 테스트는 임시 JSON 파일만 사용했다.
- 네트워크, SQLite, Kiwoom COM, 계좌 및 주문 API를 호출하지 않았다.
