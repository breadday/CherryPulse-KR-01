# TASK-026 SPEC

## 목표

Hero OpenAPI가 요구하는 32-bit Python 3.8에서 실제 `broker/kiwoom_broker.py` 모듈을 import할 수 있게 복구한다. 실행 의미를 바꾸지 않는 최소 수정인 `from __future__ import annotations`를 broker 모듈에 추가하고, Python 3.8에서 실제 소스 파일의 import 및 `main_live.py` import chain을 안전하게 검증한다.

이 작업은 import 호환성만 다룬다. `QApplication` 생성, `QAxWidget`/COM 객체 생성, 키움 연결·로그인, 계좌 동기화, 네트워크 요청 및 주문 호출은 구현과 테스트 모두에서 금지한다.

## 현재 동작과 조사 근거

- `main_live.py:3`에는 이미 `from __future__ import annotations`가 있고, `main_live.py:18`에서 `KiwoomBroker`를 import한다.
- `broker/kiwoom_broker.py`에는 postponed annotation evaluation이 없다. 그 상태에서 `broker/kiwoom_broker.py:103`의 `timeout_sec: int | None`가 Python 3.8 class body 평가 중 `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`를 발생시킨다.
- 저장소의 32-bit Python 3.8에서 PyQt 모듈만 inert fake로 대체하고 실제 broker 파일을 import한 결과, 정확히 `KiwoomBroker` class 정의의 line 103에서 위 `TypeError`가 재현됐다. fake는 Qt/COM 객체를 생성하거나 외부 연결을 하지 않았다.
- line 103만 `Optional[int]`로 바꾸는 것은 충분하지 않다. 같은 모듈의 `KiwoomBroker.get_positions`(`broker/kiwoom_broker.py:678`)와 `KiwoomBroker.get_pending_orders`(`broker/kiwoom_broker.py:710`)가 `list[dict]` 반환 annotation을 사용하며, postponed evaluation이 없으면 Python 3.8에서 다음 import-time 오류가 된다.
- `from __future__ import annotations` 한 줄은 위 세 annotation을 모두 문자열로 보존하여 Python 3.8 import-time 평가를 피하면서 함수 동작과 public signature 표기를 유지한다. 여러 annotation을 `typing.Optional`/`typing.List`로 개별 변환하는 것보다 변경 범위와 회귀 위험이 작다.
- Python 3.8의 `ast.parse(..., feature_version=(3, 8))`로 저장소 루트와 `broker`, `core`, `infra`, `strategy`, `strategies`, `selectors`, `data`, `utils`의 Python 파일 58개를 검사했으며 Python 3.8 grammar 오류는 발견되지 않았다.
- broker 소스에 future import를 메모리상 선행시킨 뒤, `QApplication`, Qt/COM 및 누락된 로컬 `requests` dependency를 inert module로 대체해 `main_live.py` import chain을 Python 3.8에서 평가한 결과 import가 완료됐다. 이 검사에서는 앱 class를 인스턴스화하지 않았다. 따라서 조사 범위에서 추가로 확인된 **언어 버전 자체의** import-time incompatibility는 없다.
- 현재 작업 환경의 Python 3.8에는 `PyQt5`와 `requests`가 설치되어 있지 않아, 실제 third-party package를 이용한 native import는 수행할 수 없었다. 이는 확인된 Python annotation 오류와 별개의 환경 dependency이며, Hero 운영 환경의 32-bit PyQt5/QAx 설치 검증은 acceptance 단계에서 별도로 해야 한다.
- 기존 `tests/test_task021_broker_timeout.py:9-31`은 Python 3.10 이상에서만 Qt fake와 broker 모듈을 준비하고, Python 3.8에서는 `BROKER_MODULE=None`과 `requires_python_310` skip을 사용한다. 호환성 복구 후에는 이 조건과 “annotations require Python 3.10+” 사유가 사실과 맞지 않으므로 제거해야 한다.
- working tree에는 TASK-026 이전의 다수 변경과 handoff 산출물이 있다. 구현자는 그 변경을 되돌리거나 정리하지 말고 아래 exact scope만 수정한다.

## 구현 범위

### 변경할 파일과 심볼

1. **`broker/kiwoom_broker.py`**
   - 파일 상단 module comment 다음, 다른 모든 import보다 앞에 `from __future__ import annotations`를 추가한다.
   - `KiwoomBroker._exec_loop_with_timeout`, `get_positions`, `get_pending_orders`의 annotation 표현과 함수 본문은 변경하지 않는다.
   - broker 초기화, `QAxWidget` 생성 위치, signal binding, timeout, TR, 로그인, 계좌 및 주문 로직은 변경하지 않는다.

2. **`tests/test_task026_python38_broker_import.py`** (신규)
   - 테스트 전용 `PyQt5.QtCore`, `PyQt5.QtWidgets`, `PyQt5.QAxContainer` fake module을 준비하여 실제 `broker/kiwoom_broker.py` 소스 파일을 import한다. production module을 복사하거나 annotation을 테스트에서 고쳐서 import해서는 안 된다.
   - fake `QApplication`과 `QAxWidget`은 생성 시 즉시 테스트를 실패시키는 sentinel이어야 한다. import만으로 두 객체가 생성되지 않았음을 call count 또는 sentinel로 검증한다.
   - broker import 후 `KiwoomBroker`가 존재하고, `_exec_loop_with_timeout.__annotations__`의 `timeout_sec`, `get_positions` 및 `get_pending_orders`의 반환 annotation이 postponed/string annotation임을 검증한다. 이 검증은 future import가 제거될 경우 Python 3.8 import 실패 또는 assertion 실패로 회귀를 잡아야 한다.
   - 동일한 inert dependency 경계에서 실제 `main_live.py` 파일을 module로 import하고 `MainLiveApp` 정의가 완료되는지 검증한다. `MainLiveApp()` 또는 module의 실행 entry point는 절대 호출하지 않는다.
   - 테스트 환경에 `requests`가 없으면 import-only fake를 사용할 수 있지만 `Session` 생성이나 HTTP 메서드를 호출해서는 안 된다. fake는 이 테스트 내부에만 한정하고 `monkeypatch`/정리 절차로 `sys.modules`를 복원하여 다른 테스트를 오염시키지 않는다.

3. **`tests/test_task021_broker_timeout.py`**
   - `sys.version_info >= (3, 10)` 조건 없이 inert Qt modules와 실제 broker module을 준비한다.
   - `requires_python_310` marker와 네 timeout 테스트의 해당 decorator를 제거한다.
   - 기존 네 테스트의 timeout 동작 및 assertion은 바꾸지 않는다. 이 파일에서도 `KiwoomBroker.__init__`을 호출하지 않고 현재의 `__new__` 방식만 유지한다.

4. **`docs/agent-handoff/TASK-026-SPEC.md`**
   - 본 구현 계약 문서다. production 변경으로 간주하지 않는다.

### 명시적 비범위

- `main_live.py`, `config_live.py`, `engine.py`, `core/*`, requirements 파일 및 실행 batch는 수정하지 않는다.
- Python 3.9/3.10 전용 annotation을 저장소 전체에서 일괄 치환하지 않는다.
- PyQt5, requests 또는 Hero OpenAPI를 설치·업그레이드하지 않는다.
- broker를 lazy import로 바꾸거나 PyQt/QAx import 실패를 production에서 fake/fallback으로 숨기지 않는다.
- 앱 시작, 로그인, 계좌조회, snapshot 로드, 실시간 등록, 네트워크 및 주문의 통합 테스트는 수행하지 않는다.

## 불변조건과 안전 제약

- `KiwoomBroker`의 runtime 동작, method parameters/defaults, return values와 annotation 텍스트의 의미는 그대로 유지한다. 변경은 annotation 평가 시점에만 영향을 줘야 한다.
- `QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")`는 계속 `KiwoomBroker.__init__`에서만 생성되어야 하며 module import 시 생성되어서는 안 된다.
- 테스트는 운영 PyQt/COM을 사용하지 않고, `QApplication`, COM control, event loop, timer 대기, broker connection/login 및 order method를 호출하지 않는다.
- 기존 TR/condition timeout과 주문 안전장치, `RUN_MODE`, `ALLOW_LIVE_ORDERS`, 조건검색 기본 비활성 및 일봉 후보 기반 흐름은 변경하지 않는다.
- third-party dependency 누락을 Python 3.8 language incompatibility로 오인하지 않는다. 운영 검증에서는 반드시 32-bit Python 3.8과 그 interpreter에 설치된 32-bit PyQt5/QAx 환경을 사용한다.
- 테스트 fake를 production 코드에 넣지 않으며, fake module 상태가 다른 테스트로 누출되지 않아야 한다.
- baseline 이전 working-tree 변경, `.env`, 계좌정보, 생성 DB/로그 및 기존 handoff 파일을 수정·삭제하지 않는다.

## 인수 테스트

### 1. Focused test (안전한 import-only)

먼저 32-bit Python 3.8 interpreter임을 명시적으로 확인한다.

```powershell
py -3.8-32 -c "import struct, sys; print(sys.version); assert sys.version_info[:2] == (3, 8); assert struct.calcsize('P') * 8 == 32"
py -3.8-32 -B -m pytest -q tests/test_task026_python38_broker_import.py tests/test_task021_broker_timeout.py
```

필수 결과:

1. 실제 `broker/kiwoom_broker.py` import가 line 103의 `TypeError` 없이 성공한다.
2. `_exec_loop_with_timeout`의 `int | None` 및 두 method의 `list[dict]` annotation이 import 시 평가되지 않고 postponed annotation으로 남는다.
3. 실제 `main_live.py` import chain이 Python 3.8에서 완료된다.
4. import 동안 `QApplication`과 `QAxWidget` 생성 횟수는 0이며 COM, 로그인, 계좌, network, timer/event-loop 및 주문 호출도 0이다.
5. 기존 TASK-021 네 timeout 테스트가 Python 3.8에서 skip 없이 통과한다.

### 2. Failure-path/회귀 테스트

- future import를 제거한 임시 mutation 또는 reviewer의 독립 확인에서는 focused broker import가 line 103 `TypeError`로 실패해야 한다. production 파일을 실제로 되돌린 채 남기지 않는다.
- fake `QApplication`/`QAxWidget` constructor가 import 중 호출되면 sentinel assertion으로 즉시 실패해야 한다. 이는 import test가 실수로 앱/COM 초기화를 시작하는 회귀를 검출한다.
- canonical broker module을 사전 주입한 뒤 main import를 수행하여 main chain이 테스트용으로 annotation을 수정한 별도 broker 사본을 사용하지 않음을 확인한다.
- Python 3.8 interpreter가 없거나 64-bit interpreter가 선택되면 version/bitness preflight가 실패해야 하며, Python 3.10 결과를 Python 3.8 검증으로 보고해서는 안 된다.
- 운영 Hero 환경에서 PyQt5/QAx import 자체가 실패하면 annotation 수정 성공과 구분하여 dependency/bitness 설치 문제로 보고한다. 이를 production fallback으로 우회하지 않는다.

### 3. Syntax 및 regression 검증

```powershell
py -3.8-32 -B -c "from pathlib import Path; files=['broker/kiwoom_broker.py','main_live.py']; [compile(Path(p).read_text(encoding='utf-8-sig'), p, 'exec') for p in files]; print('python 3.8 syntax ok')"
py -3.8-32 -B -m pytest -q
py -3.10-32 -B -m pytest -q tests/test_task026_python38_broker_import.py tests/test_task021_broker_timeout.py
git diff --check -- broker/kiwoom_broker.py tests/test_task026_python38_broker_import.py tests/test_task021_broker_timeout.py docs/agent-handoff/TASK-026-SPEC.md
git status --short
```

전체 suite 실패가 dependency 또는 baseline의 기존 변경 때문이면 TASK-026 회귀와 분리해 정확히 기록한다. `main_live.py`를 실행하거나 live/paper broker 동작을 검증했다고 주장하지 않는다.

### 4. Hero 운영환경의 실제 dependency import 확인

구현 후 실제 Hero용 32-bit Python 3.8 환경에서, 장 시작 프로그램이나 `MainLiveApp`을 실행하지 않고 다음 import-only 명령만 수행한다.

```powershell
py -3.8-32 -B -c "import broker.kiwoom_broker as kb; print(kb.KiwoomBroker.__name__)"
```

이 명령은 해당 interpreter에 실제 32-bit PyQt5/QAx가 설치된 경우에만 수행한다. `KiwoomBroker()`를 생성하지 않으므로 `QAxWidget`, COM 연결 및 로그인은 시작하지 않는다. 성공 기준은 `KiwoomBroker` 출력과 process exit code 0이다.

## 롤백 고려사항

- 회귀가 생기면 TASK-026의 broker future import와 두 테스트 파일 변경만 되돌린다. 다른 working-tree 변경은 건드리지 않는다.
- production rollback은 Python 3.8 import failure를 즉시 다시 만들므로 Hero 운영환경에서는 rollback 전에 프로세스를 시작하지 말고, 원인 확인 후 수정본을 재배포한다.
- 테스트 fake는 runtime artifact가 아니므로 운영 배포물이나 `sys.path`에 포함시키지 않는다.
- rollback 과정에서 Python 버전을 3.10으로 올리는 것은 Hero OpenAPI 제약의 해결책이 아니며 허용하지 않는다.
