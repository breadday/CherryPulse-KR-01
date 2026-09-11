# TASK-011 테스트 보고서

## 실행 결과

- 초기 red 확인: `python -m pytest -q tests/test_task011_recovery_isolation.py`에서 pending query isolation 테스트가 실패했고, A/B event가 모두 `MANUAL_INTERVENTION_REQUIRED`가 되는 결함을 재현했다.
- 수정 후 전용 테스트: `12 passed in 0.25s`
- 전체 테스트: `53 passed in 104.00s`
- 문법 검사: `syntax ok`
- `git diff --check -- engine.py`: 통과. Git은 기존 작업 파일의 LF/CRLF 변환 경고만 표시했다.

## acceptance 결과

- 14:39/14:40/14:41 및 15:19/15:20/15:21/15:34에서 recovery 호출이 허용됨을 확인했다.
- 15:35/15:36에서 direct recovery가 broker connect를 호출하지 않음을 확인했다.
- heartbeat에서 `auto_shutdown`이 risk observation과 pending management보다 먼저 실행됨을 확인했다.
- shutdown에서 engine gate가 reconciliation보다 먼저 설정됨을 확인했다.
- 공유 pending query failure에서 두 event 모두 원래 `SELL_SUBMITTING` 상태를 유지함을 확인했다.

## 제한

호스트 기본 Python은 3.8이며 프로젝트 `.venv`는 존재하지 않았다. `main_live` 테스트는 PyQt/QtAx, broker transport, Telegram 네트워크를 stub으로 격리해 실행했다. 실제 Kiwoom/COM 및 주문 경로는 실행하지 않았다.
