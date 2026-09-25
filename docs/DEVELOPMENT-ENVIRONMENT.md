# Windows 개발 환경

로컬 PC에서 실행할 단계별 검사와 결과 전달 양식은
[키움 로컬 검증 안내](KIWOOM-LOCAL-VERIFICATION-GUIDE.md)를 따른다.

2026-09-14. 새 실행 엔진을 개발하기 위한 환경이며 자동매매 프로그램 자체는 아직 구현하지 않았다.

## 확인된 구성

| 구성 | 버전·위치 |
|---|---|
| Python | 3.10.8, 32비트 |
| 프로젝트 환경 | .venv, 시스템 site-packages 비공유 |
| PyQt5 | 5.15.11 |
| Qt | PyQt5-Qt5 5.15.2 |
| SIP | PyQt5-sip 12.18.0 |
| uv | 0.12.13, .tools/uv/uv.exe |
| 선언·잠금 | ../pyproject.toml, ../uv.lock |

uv는 공식 GitHub 릴리스 ZIP과 해당 SHA-256 파일을 내려받아 해시 일치 후 프로젝트 .tools/에 압축 해제했다. 시스템 PATH·기존 Python·키움 설치·계좌 설정을 변경하지 않았다. [.tools 설치 방식의 공식 설명](https://docs.astral.sh/uv/getting-started/installation/#github-releases).

.tools/, .uv-cache/, .venv/는 로컬 산출물이며 Git에서 제외한다. pyproject.toml과 uv.lock은 재현을 위한 소스 파일이다. uv.lock은 uv가 생성했으며 수동 편집하지 않는다.

## 재구성

프로젝트 루트의 PowerShell에서 실행한다. 아래 Python은 이 PC에서 확인된 설치다. 다른 PC에서는 설치된 **32비트 Python 3.10**의 명시적 경로를 사용하고 아래 검사를 다시 수행한다. pyproject의 Python 버전 범위만으로 32비트가 강제되는 것은 아니다.

```powershell
$enginePython = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310-32\python.exe'
& .\.tools\uv\uv.exe sync --frozen --python $enginePython --no-python-downloads --cache-dir .uv-cache --default-index https://pypi.org/simple
```

uv 실행 파일이 없는 PC에서는 공식 릴리스의 0.12.13 Windows 실행 파일을 준비한다. 현재 .tools에는 uv.zip과 uv.zip.sha256도 남아 있다. 인터넷으로부터 받은 실행 파일을 변경된 경로에 무검증 설치하지 않는다.

## 주문 없는 호환 검사

다음 명령은 새 환경에서 Python 비트 수·격리·Qt 버전을 출력하고, 보이지 않는 QAxWidget에 키움 컨트롤을 생성한 뒤 해제한다. QApplication 이벤트 루프·로그인·계좌 조회·SendOrder를 호출하지 않는다. back/ 모듈과 .env를 읽지 않는다.

```powershell
& .\.venv\Scripts\python.exe -I -B -c 'import sys,struct,importlib.metadata as m; from PyQt5.QtWidgets import QApplication; from PyQt5.QAxContainer import QAxWidget; print(sys.version.split()[0],struct.calcsize("P")*8,sys.prefix!=sys.base_prefix); print(m.version("PyQt5"),m.version("PyQt5-Qt5"),m.version("PyQt5-sip")); app=QApplication([]); control=QAxWidget(); ok=control.setControl("KHOPENAPI.KHOpenAPICtrl.1"); print("control_created",ok,"is_null",control.isNull()); control.clear(); print("control_released",control.isNull()); raise SystemExit(0 if ok and struct.calcsize("P")==4 and sys.prefix!=sys.base_prefix else 1)'
& .\.tools\uv\uv.exe pip check --python .venv\Scripts\python.exe --cache-dir .uv-cache
```

## 이번 실행 결과

- Python: 3.10.8, bits32, isolated=True.
- QtCore 로드 위치: 프로젝트 .venv/lib/site-packages/PyQt5/QtCore.pyd.
- control_created=True, is_null=False, control_released=True, 종료 코드0.
- uv 의존성 검사: 패키지3개 호환, 종료 코드0.
- uv sync --frozen --offline: 기존 캐시로 잠금 상태 확인, 종료 코드0.
- 이후 내부 원장 구현에서 검사 도구를 추가 설치·실행했다. 현재 버전과 명령은 아래 개발 도구 절을 따른다.

이 결과는 COM 생성 호환성까지다. 실제 로그인·시세·접수·체결·취소·복구·계좌 인계·실거래 안전성을 확인한 결과가 아니다. Q01~Q09 및 Q11~Q13은 유지하고 Q10 중 로컬 Python/Qt/COM 생성만 확인된 것으로 본다.

## 내부 원장 개발 도구 — 2026-09-14 추가

실행 환경에 Pydantic 2.13.5, typing-extensions 4.16.0을 추가했다. 개발 그룹은 pytest 9.1.1, Ruff 0.16.7이며 uv.lock에 고정했다. 기존32비트 Python/Qt 구성은 유지한다. 앞의 COM 검사 결과는 환경 구성 당시 기록이며 새 원장 검사와 구별한다.

basedpyright 1.40.1의 Python 배포판은32비트 환경에서 Node 의존성 빌드가 실패했다. 따라서 이미 설치된64비트 Node를 사용해 검사 도구만 별도 설치한다. 프로젝트의 실행용 Python이나 시스템 패키지를 변경하지 않는다.

```powershell
& .\.tools\uv\uv.exe pip install --no-deps --target .tools/typecheck basedpyright==1.40.1 --python .venv/Scripts/python.exe --cache-dir .uv-cache
& node .tools/typecheck/basedpyright/index.js --pythonpath .venv/Scripts/python.exe
```

반드시 `index.js`를 실행한다. `dist/pyright.js`를 직접 실행하면 패키지의 typeshed 기준 경로가 설정되지 않아 잘못된 표준 라이브러리 진단이 발생한다. basedpyright는 실행 패키지가 아니므로 uv.lock의 실행 의존성에 넣지 않았으며 위 명령으로 별도 버전을 고정한다.

## 원장 검증 명령

```powershell
& .\.venv\Scripts\ruff.exe check execution tests
& .\.venv\Scripts\ruff.exe format --check execution tests
& node .tools/typecheck/basedpyright/index.js --pythonpath .venv/Scripts/python.exe
$ledgerTestTemp = Join-Path '.tools' ('pytest-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -m pytest -q --tb=line --basetemp $ledgerTestTemp
& .\.venv\Scripts\python.exe -m execution
& .\.tools\uv\uv.exe pip check --python .venv/Scripts/python.exe --cache-dir .uv-cache
```

기존 테스트 폴더를 basetemp로 지정하지 않는다. 매번 고유 폴더를 생성한다. 이번 실행에서는 기본 임시 경로를 쓰는 일부 검사 호출이 도구 제한시간을 넘겼고, 작업영역 내부의 고유 임시 경로에서는 전체 검사를 정상 완료했다. 외부 pytest 플러그인 자동 로딩을 끈 상태에서도 확인했다.

현재 결과는 [내부 원장 구현 기록](REBUILD-04-LOCAL-LEDGER.md)에 정리했다. `.tools/`와 테스트 DB는 Git 제외 대상이다. 체크아웃·시스템 환경이 달라지면 위 검사를 다시 수행한다.

## 2026-09-25 현재 작업공간 재검사

이번 세션에서 저장소 `.venv`, `.tools/uv/uv.exe`,
`.tools/typecheck/basedpyright/index.js`는 사용할 수 없었다.
사용자 설치 Python 3.10.8 32비트(현재 import된 Pydantic 2.13.5, pytest 9.1.1,
Ruff 설치)를 사용해 pytest **159 passed**, `ruff check execution tests`,
`ruff format --check execution tests`, `python -m execution`, `pip check`를
실행했고 모두 통과했다. 이 결과는 현재 설치의 Windows 전체 소프트웨어
회귀이며 격리 `.venv`·uv 잠금 재현 검사를 대체하지 않는다. basedpyright와
브라우저/Chromium 도구는 발견되지 않았고 설치하지 않았다.
