# TASK-026 TEST

## 실행 결과

- 사용자의 Python 3.8 32-bit PowerShell 환경에서 focused pytest를 실행했다.

```text
task026 direct import harness: passed
task021 direct timeout harness: passed
```

```text
py -3.8-32 -m pytest -q tests/test_task026_python38_broker_import.py tests/test_task021_broker_timeout.py
5 passed in 0.14s
```

```text
py -3.8-32 -B -c "import broker.kiwoom_broker as kb; print(kb.KiwoomBroker.__name__)"
KiwoomBroker
```

```text
py -3.8-32 -B -m pytest -q
110 passed, 18 skipped in 118.05s (0:01:58)
```

The focused broker import suite covers CP949 mojibake repair and after-close shutdown reconciliation: `3 passed`.

- TASK-026 pytest는 실제 `broker/kiwoom_broker.py`와 `main_live.py`를 import했고, annotation 문자열과 `MainLiveApp` 정의를 확인했다.
- inert `QApplication`/`QAxWidget` 생성 호출은 0건이었다.
- TASK-021 네 timeout 테스트와 TASK-026 import 테스트가 모두 통과했다.
- 변경 파일 3개의 UTF-8 syntax compile 및 `git diff --check`가 통과했다.

## 미실행 검증

- Python 3.8 전체 pytest suite가 통과했다. syntax compile은 별도 명령으로 확인할 수 있다.
- live/paper 계좌, COM 연결, 로그인, 네트워크 및 주문은 사양대로 실행하지 않았다.
