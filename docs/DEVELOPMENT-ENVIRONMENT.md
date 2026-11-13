# 개발 환경 — REST API 기준

갱신일: 2026-11-11

## 기준 런타임

- 64-bit Python 3.15 (`pyproject.toml`: `>=3.15,<3.16`).
- 의존성 잠금: `uv.lock`; uv 버전은 프로젝트 설정을 따른다.
- CI의 REST 및 Windows 회귀 job은 Python 3.15를 사용한다.
- REST 인증·조회는 HTTP API, 실시간 수신은 WebSocket 경계를 사용한다.
- Kiwoom COM/ActiveX는 활성 런타임에서 제외했다. `verify_kiwoom_com.py`, `verify_kiwoom_connection.py`, `verify_kiwoom_readonly.py`, `tools/inspect_kiwoom_realtime.py`는 실행 시 `COM_RETIRED_REST_ONLY`로 종료하며 PyQt5/OCX를 불러오지 않는다.
- COM control 생성 자체는 REST로 대체할 수 없다. REST 계좌 조회는 `tools.probe_kiwoom_rest`, 실시간 시세 관측은 `tools.probe_kiwoom_ws`를 사용하되, 각각 기본 오프라인 모드다. 실제 네트워크 요청은 명시적 `--execute-read-only`와 별도 사용자 승인이 필요하다. 구형 TR과 REST API ID가 일대일 대응한다고 가정하지 않는다.

## 준비·검사

저장소 루트에서:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-rest"
uv sync --frozen --python 3.15
uv pip install --python .venv-rest\Scripts\python.exe -r tools/requirements-rest-probes.txt
.venv-rest\Scripts\python.exe -m pytest -q --tb=short
.venv-rest\Scripts\python.exe tools\verify_rest_migration.py
```

예약 실행기 `scripts/r045-morning-run.cmd`는 `.venv-rest`를 사용하므로, probe 추가 의존성과 실행 모두 같은 interpreter에 맞춘다.

COM 전용 도구를 다시 활성화하거나 `.venv-rest`에 PyQt5/QAxContainer를 추가하지 않는다. 보관된 COM 구현은 과거 코드 참고용이며 현재 실행·운영 지침이 아니다.

실행 확인은 실제 네트워크 인증·계좌 조회와 분리한다. 네트워크 없는 verifier와 테스트는 합성 응답만 사용한다. 실제 계좌·증권사 호출은 별도 승인과 실증 체크리스트가 있을 때만 수행한다.

## 검증 범위 구분

- 소프트웨어: pytest, REST verifier, Ruff, basedpyright, Node 테스트와 빌드 dry-run.
- 증권사: 실제 모의계좌 응답·페이지 완전성·식별 근거·장중 WebSocket 수신. 오프라인 검증으로 대체할 수 없다.
- 운영: 계좌 인계·예약 작업·실주문·배포. 별도 승인 없이는 실행하지 않는다.
