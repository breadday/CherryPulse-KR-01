# TASK-025 IMPLEMENTATION

## 변경 내용

- `config_live.py`에 기본 비활성인 `ENABLE_EXTERNAL_UNIVERSE`와 기본 파일명 `external_candidates.json`을 추가했다.
- 환경변수는 `1`, `true`, `yes`, `on`만 활성값으로 해석한다.
- `main_live.py`는 활성 상태에서만 프로젝트 루트 기준 외부 후보 경로를 `UniverseManager`에 전달한다.
- 계좌와 미체결 주문 동기화 및 snapshot 처리 후, 조건검색 시작 전에 외부 후보를 로드한다.
- 성공 및 실패 시 실시간 등록을 동기화하며, 실패 시 비워진 external source를 SQLite에도 반영해 이전 후보가 남지 않게 했다.
- 실패 후 실시간 등록, SQLite 저장, 요약 로그를 각각 격리해 후처리 하나의 오류가 시작 흐름을 중단하지 않게 했다.
- 전략별 external 후보 수와 활성 상태를 로그에 추가했다.
- Python 3.8 단위 테스트에서는 Qt, Kiwoom COM, Telegram, SQLite, 주문 경로를 가짜 객체로 격리했다.

## 안전성

- 기본값에서는 외부 파일을 읽거나 provider를 만들지 않는다.
- 외부 후보 오류는 시작 흐름으로 전파하지 않고 external source만 비운다.
- 이전 external 후보 제거, snapshot 보존, 보유·미체결 종목 라우팅 보존을 단위 테스트로 확인했다.
- 조건검색 기본값과 주문 및 리스크 설정은 변경하지 않았다.
- `main_live.py`와 실제 Kiwoom API는 실행하지 않았다.

## 잔여 사항

- 기존 `broker/kiwoom_broker.py`의 `int | None` 타입 표기는 Python 3.8에서 import 오류를 일으킨다. TASK-025 수정 권한 밖이라 변경하지 않았다.
