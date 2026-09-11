# TASK-014 IMPLEMENTATION

## Changed files

- `.github/workflows/ci.yml`
  - push와 pull request에서 동작하는 Windows CI를 추가했다.
  - repository 권한을 contents read로 제한했다.
  - Python 3.10 x86을 명시하고 PowerShell parser, Python compileall, 전체 pytest를 순서대로 실행한다.
- `requirements-test.txt`
  - 헤드리스 테스트에 필요한 pytest 7.4.4만 고정했다.
- `docs/agent-handoff/TASK-014-SPEC.md`
  - CI 범위와 거래 안전 제약을 기록했다.

## Design notes

- 테스트가 임시 저장소에서 Windows PowerShell runner와 `opencode.cmd` stub을 실행하므로 `windows-latest`를 사용한다.
- 로컬 운영 환경과 같은 Python 3.10 32비트 조건을 사용한다.
- PyQt5와 Kiwoom COM은 CI에서 설치하거나 실행하지 않는다. 기존 테스트가 GUI와 broker transport를 stub 처리하므로 안전 회귀 테스트에는 `pytest`만 필요하다.
- GitHub Actions 공식 사용 예시에 맞춰 `actions/checkout@v7`과 `actions/setup-python@v7`을 사용한다.

## Safety

- 거래 로직, `.env`, broker transport, live trading 활성화 경로는 변경하지 않았다.
- `main_live.py`는 컴파일만 하며 실행하지 않는다.
