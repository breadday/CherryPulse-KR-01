# TASK-026 IMPLEMENTATION

## 변경 내용

- `broker/kiwoom_broker.py`에 `from __future__ import annotations`를 추가해 Python 3.8 import 시 현대 annotation 표현이 평가되지 않도록 했다.
- `tests/test_task021_broker_timeout.py`의 Python 3.10 전용 조건과 skip decorator를 제거하고 동일한 네 timeout assertion을 모든 지원 Python에서 실행하도록 했다.
- `tests/test_task026_python38_broker_import.py`를 추가해 실제 broker/main 소스 import, postponed annotations, inert Qt/COM 경계를 검증한다.

## 안전성

- broker 초기화, `QAxWidget`, `QApplication`, COM, 로그인, 네트워크 및 주문 경로는 import 테스트에서 호출하지 않는다.
- TASK-026 지정 파일 외 production 로직과 주문 안전장치는 변경하지 않았다.
