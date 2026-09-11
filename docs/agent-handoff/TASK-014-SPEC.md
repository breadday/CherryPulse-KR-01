# TASK-014 SPEC

## Goal

현재 안전 회귀 검증을 GitHub Actions에서 자동 재현한다.

## Scope

- Windows runner에서 PowerShell 스크립트 구문을 검사한다.
- Python 3.10 32비트에서 프로젝트 Python 소스를 컴파일하고 전체 pytest를 실행한다.
- 테스트 전용 의존성은 운영 의존성과 분리하고 버전을 고정한다.

## Safety constraints

- `.env`, broker transport, live trading 활성화와 주문 경로를 변경하지 않는다.
- `main_live.py` 또는 Kiwoom COM을 실행하지 않는다.
- CI 권한은 repository contents read로 제한한다.

## Acceptance criteria

- push와 pull request에서 Windows CI가 실행된다.
- 모든 `scripts/*.ps1` 파일이 PowerShell parser를 통과해야 한다.
- 핵심 Python 경로와 테스트가 `compileall`을 통과해야 한다.
- 전체 pytest가 통과해야 한다.
