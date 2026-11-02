# 개발 환경 — REST API 기준

갱신일: 2026-11-02

## 기준 런타임

- 64-bit Python 3.15 (`pyproject.toml`: `>=3.15,<3.16`).
- 의존성 잠금: `uv.lock`; uv 버전은 프로젝트 설정을 따른다.
- CI의 REST 및 Windows 회귀 job은 Python 3.15를 사용한다.
- REST 인증·조회는 HTTP API, 실시간 수신은 WebSocket 경계를 사용한다.

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

실행 확인은 실제 네트워크 인증·계좌 조회와 분리한다. 네트워크 없는 verifier와 테스트는 합성 응답만 사용한다. 실제 계좌·증권사 호출은 별도 승인과 실증 체크리스트가 있을 때만 수행한다.

## 검증 범위 구분

- 소프트웨어: pytest, REST verifier, Ruff, basedpyright, Node 테스트와 빌드 dry-run.
- 증권사: 실제 모의계좌 응답·페이지 완전성·식별 근거·장중 WebSocket 수신. 오프라인 검증으로 대체할 수 없다.
- 운영: 계좌 인계·예약 작업·실주문·배포. 별도 승인 없이는 실행하지 않는다.
