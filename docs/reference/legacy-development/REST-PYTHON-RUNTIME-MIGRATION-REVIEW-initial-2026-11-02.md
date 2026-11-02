# REST 런타임 최신 Python 전환 검토

작성일: 2026-11-02
상태: 검토·제안 문서. 런타임·코드·예약 작업은 이 문서 작성만으로 변경하지 않음.

## 결론

**REST API를 쓰기 위해 Python 3.10을 계속 사용할 필요는 없다.** HTTP REST와 WebSocket은 현재 Kiwoom REST 인터페이스 계약과 인증을 따르는 것이 핵심이며, Python 3.10은 API 요구사항이 아니라 저장소와 R045 실행기의 현재 런타임 선택이다.

Python 3.10 계열은 2026-10-01 지원 종료됐고, 현재 실행 PC의 `py -3.10`은 3.10.8이다. 2026-11-02 현재 Python 최신 릴리스는 3.15.2이며 3.15 계열은 bugfix 지원 중이다. Windows에는 64비트와 32비트 배포판이 있다.[1][2][4] 따라서 REST 전용 실행환경을 지원되는 Python으로 옮기는 것이 타당하다. 다만 **현 코드에 `py -3.15`만 치환하는 것은 안전한 전환이 아니다.** 저장소 전체가 아직 Python 3.10에 고정되어 있고, 기존 PyQt/ActiveX 검사 경로와 REST 실행환경이 한 프로젝트 설정에 섞여 있다.

권고안은 **REST/WS 실행환경을 별도 64비트 가상환경으로 분리하고, 우선 Python 3.15.2에서 호환성 검증을 수행하는 것**이다. 3.15 의존성·도구가 준비되지 않으면 Python 3.14.10을 지원 중인 임시 호환 기준으로 검증한다. Python 3.15.2 적합성을 테스트하기 전 운영 예약 실행기의 기본값으로 확정하지 않는다.

## 저장소에서 확인한 현재 상태

| 영역 | 확인 내용 | 영향 |
|---|---|---|
| Python 정책 | `pyproject.toml`은 `>=3.10.8,<3.11`, Ruff `py310`, basedpyright `pythonVersion = "3.10"` | 루트 개발·검증 환경은 3.15 실행을 허용하지 않음 |
| 혼합 의존성 | 같은 `pyproject.toml`에 Pydantic과 PyQt5/Qt/SIP가 함께 선언됨 | REST 환경에 GUI/COM 계열 전체 의존성을 끌고 갈 이유가 있는지 import 경계 조사 필요 |
| REST 의존성 | `tools/requirements-rest-probes.txt`는 `typing-extensions==4.16.0`, `websockets==15.0.1`이며 주석은 Python 3.10 설치를 지시 | 별도 REST manifest로 분리하기 좋은 출발점이나, 실제 import closure 검증 전 완전한 의존성 목록으로 간주하지 않음 |
| 예약 실행기 | `scripts/r045-morning-run.cmd`가 `py -3.10 -m tools.r045_morning_run` 실행 | 버전 선택은 이 wrapper에서 고정됨. runner 내부의 자식 Python 호출은 `sys.executable`을 사용하므로 같은 interpreter로 유지 가능 |
| 오프라인 verifier | `.github/workflows/rest-migration.yml`의 두 job 모두 Python 3.10 사용 | 새 Python 테스트가 CI에 없고, Windows 엔진 회귀와 REST 검증이 같은 버전으로 묶여 있음 |
| REST 구현 | `adapters/kiwoom_rest_auth.py`, `kiwoom_rest_transport.py`, `kiwoom_rest_ws.py`; `tools/probe_kiwoom_rest.py`, `probe_kiwoom_ws.py` | 명시적 probe 경로는 존재함. REST 전환 전체 완료를 뜻하지 않음 |
| R04–R06 상태 | STATUS에서 R04 계좌 식별/대조 미확인, R05 도구 오프라인 검증, R06 `VIRTUAL_ONLY_REST_UNCONNECTED` | 런타임 업그레이드는 증권사 실측·주문 연결·보호 dispatcher 완료를 대신하지 않음 |

REST transport는 `urllib.request`로 `mockapi.kiwoom.com`의 고정 모의 호스트를 호출하고, 조회 프로브는 기본값에서 네트워크를 쓰지 않는다. WebSocket 프로브 또한 명시적 실행을 요구한다. 코드 경계와 호출 대상은 별개 검증이 필요하다. 이 검토에서 브로커를 호출하거나 예약 runner를 실행하지 않았다.

## 용어·범위 구분

- `py -3.10`은 Windows Python launcher에 특정 Python 계열을 선택하는 명령이다. REST API를 선택하거나 활성화하는 설정이 아니다.
- **REST API 전환**은 브로커 통신 경로를 REST/WS 어댑터로 연결하는 설계·검증 작업이다.
- **Python 런타임 전환**은 그 코드를 실행할 Python 버전·아키텍처·패키지 집합을 바꾸는 별도 작업이다.
- 그러므로 Python을 3.15로 올려도 R06의 실제 엔진 연결이 저절로 생기지 않는다. 반대로 REST 어댑터는 API 조건을 만족하는 동안 Python 3.10 외 버전에서도 실행 가능하도록 설계·검증할 수 있다.

## 권고 구조

### A. REST 전용 64비트 환경

프로젝트 루트 GUI/엔진 환경과 구분되는 전용 환경(예: `.venv-rest`)을 만든다. R045 wrapper는 확인된 가상환경 interpreter를 명시적으로 실행하고, `tools.r045_morning_run`이 자식 probe를 `sys.executable -m ...`으로 실행하는 현재 구조를 유지한다. 전환 뒤에는 실제 wrapper와 예약 작업 Action/Start-in 경로가 같은 interpreter를 가리키는지 확인한다.

REST 런타임과 테스트·정적검사 도구의 dependency manifest를 정리한다. 현재 REST probe 의존성 파일은 production 전체의 의존성 보증 파일이 아니다. 테스트 import graph에 필요한 런타임·pytest·Ruff·type checker를 분리해 고정하고 clean install 및 `pip check`를 통과시킨다.

### B. 프로젝트 설정 분리

전환 구현 시 다음 중 하나를 선택한다. 현재는 결정하지 않는다.

1. **REST 우선 재구성(권고):** 루트의 REST 런타임/검증 기준을 지원 중인 Python으로 올린다. PyQt5와 COM 검증은 실제 활성 경로인지 import·실행 추적으로 확인한 뒤 별도 격리 또는 폐기한다. `back/` 보관 자료는 활성 모듈로 복원하지 않는다.
2. **일시적 두 환경:** REST는 새 64비트 Python, 아직 필요한 OCX/COM 로컬 검사는 기존 32비트 환경에서만 수행한다. 단, 사용자가 요구한 최종 목표가 Python 3.10 완전 제거라면 이 상태는 이행 중 단계일 뿐 완료가 아니다.

PyQt5 5.15.11에는 Windows `abi3` wheel이 있으나, wheel tag만으로 현재 고정한 Qt/SIP 조합이나 QAx/OCX 상호작용의 최신 Python 호환성을 증명할 수 없다.[3] REST-only dependency 환경에서는 PyQt를 불필요하게 설치하지 않는 것이 우선이며, COM을 보존할 경우 별도 실측이 필요하다.

### C. 활성 Python 3.10 참조 정리

실제 전환 후 활성 실행경로·설치안내·체크리스트·CI에서 3.10 강제를 제거한다. 현재 확인된 주요 수정 대상은:

- `pyproject.toml`: `requires-python`, Ruff target, basedpyright Python target 및 의존성 그룹.
- `scripts/r045-morning-run.cmd`: 3.10 launcher 대신 REST venv interpreter를 고정.
- `tools/requirements-rest-probes.txt`: Python 3.10 주석과 의존성 소유권을 새 REST manifest로 이관.
- `.github/workflows/rest-migration.yml`: REST 검증을 새 Python x64 기준으로 수행하고 Windows 전체 회귀도 해당 지원 버전에서 검증.
- 현행 실행 안내: `docs/사용법.md`, `REST-R02-AUTH-READONLY.md`, `REST-R03-WEBSOCKET.md`, `REST-R04-LIVE-PROBE-CHECKLIST-2026-10-21.md`, `REST-MIGRATION-PLAN.md`, 자동개발 지시서 등.

과거 검증의 interpreter/version 사실은 재현 이력으로 보존한다. 완료된 과거 결과에 적힌 `py -3.10` 문자열을 일괄 치환하면 당시 검증 기록이 거짓이 되므로, 과거 기록은 수정하지 않고 **현재 명령이 아닌 역사 기록**임을 표시한다. 새 상태 문서와 실제 운영 안내에는 이전 명령을 실행 예시로 남기지 않는다.

## 단계별 이행 및 통과 기준

### 0. 현행 실행 확인 — 읽기 전용

- 예약 작업의 실제 실행 파일, argument, Start-in, 실행 계정, 마지막/다음 실행을 확인한다.
- 현재 R045 작업은 조건을 만족하면 모의 1주 지정가를 제출할 수 있는 side-effecting runner다. 런타임 이관 테스트를 위해 예약 실행·강제 실행·취소를 하지 않는다.
- 설치된 Python 3.15.2 x64와 전용 venv가 이미 있는지 확인한다. 설치가 없다면 승인받기 전 사용자 시스템에 설치하지 않는다.

### 1. 의존성·import 감사

- REST probe / morning runner에서 transitively import되는 모든 모듈과 플랫폼 의존성을 고정한다.
- `PyQt5`, QAx, Windows-only 모듈이 REST runtime/test 경로에 끌려오는지 확인한다.
- `typing-extensions`, `websockets`, `pydantic`, pytest, Ruff, basedpyright의 선택 버전이 새 Python에 실제 설치·실행되는지 확인한다. 단순 metadata 허용이나 wheel 존재를 성공으로 간주하지 않는다.

### 2. 격리된 Python 3.15.2 호환성 시도

- 저장소 전용 64-bit REST venv에서 `sys.version`, `sys.executable`, pointer width를 검사한다.
- 실제 토큰·계좌 정보 없이 전체 REST 오프라인 테스트, type check, lint/format, verifier와 runner child-command 구성을 검사한다.
- `tools/r045_morning_run.py`가 자식 실행에 동일 venv interpreter를 전달하는지 합성 executor 테스트로 확인한다.
- 3.15에서 dependency/build/API 문제가 발견되면 원인을 기록한다. 자동으로 3.10으로 회귀하지 않고 지원 중인 3.14.10 대체 검증을 별도 결과로 수행한다.

### 3. 코드·CI·문서 변경

- RED→GREEN 회귀검사로 wrapper interpreter 선택, clean environment, runner 자식 interpreter, verifier, full pytest를 검증한다.
- Python 정책, REST dependency lock/manifest, CI, 활성 안내를 한 작업 단위로 맞춘다.
- Windows full regression, `pytest`, REST verifier, Ruff check/format, basedpyright, `pip check`, Node 테스트/build dry-run을 새 interpreter에서 수행한다.
- repository-wide active configuration/source search 결과에 `py -3.10`, `<3.11`, `pythonVersion = "3.10"`, 3.10 CI pin이 남지 않았음을 확인한다. 과거 인계·결과 문서와 archive의 명시적 역사 기록은 허용 목록으로 분류한다.

### 4. 예약 작업 반영 — 별도 감독·명시 승인

- 새 wrapper가 지정된 경로를 가리키고 새 interpreter에서 오프라인 사전검사를 통과하기 전에는 예약 작업 Action을 바꾸지 않는다.
- 작업 scheduler의 실제 Action 변경은 이 검토 문서만으로 승인하지 않는다. 변경 시 3.10 fallback은 주문 runner가 호출되지 않는 읽기 전용 오류 처리로 설계하고, 스케줄러의 다음 실행 및 log 경로를 사람이 확인한다.
- 코드/CI 통과를 모의계좌 API 통과로 승격하지 않는다. 실제 API 조회는 기존 R04 체크리스트와 명시된 계좌 승인에 따라 별도 수행한다. 주문·취소·배포는 별도 승인이 필요하다.

## 승인 전제 및 미완료

이 문서는 Python 3.15.2를 **후보**로 제시하며, 호환성 승인 또는 구현 지시가 아니다. 다음은 아직 하지 않았다:

- Python 설치, venv 생성, 의존성 설치 또는 `pyproject.toml` 변경.
- wrapper, CI, 예약 작업, live-probe 체크리스트/실행 안내 변경.
- 새 Python에서의 test/ruff/typecheck 결과 확보.
- 지정 PC 예약 작업 조회, 실제 증권사 호출, 주문·취소, 운영 배포.

구현 수락 기준은 새 지원 Python에서 오프라인 검사와 Windows 전체 회귀가 통과하고, 활성 경로에 3.10 고정이 없으며, 지정 PC의 예약 Action이 검증된 REST venv를 가리키고, R04/R05/R06의 실제 증권사 상태는 별도로 정확히 표시되는 것이다.

## 근거 출처

Python 3.15.2 릴리스 및 Windows 32/64-bit 설치 파일, 현재 지원표, PyQt5 wheel metadata를 확인했다. 지원 종료일은 계획표의 명시 날짜를 사용했다.

## Sources

[1] https://www.python.org/downloads/release/python-3152 — Python 3.15.2 release (2026-10-25)
[2] https://devguide.python.org/versions/ — Python branch support lifecycle; Python 3.10 EOL 2026-10-01, 3.15 bugfix support through 2031-10
[3] https://pypi.org/project/PyQt5/5.15.11/ — PyQt5 5.15.11 Windows wheel tags
[4] https://www.python.org/downloads/windows/ — Windows Python releases/installers
