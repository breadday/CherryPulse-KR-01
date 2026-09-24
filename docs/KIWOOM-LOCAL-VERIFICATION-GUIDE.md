# 키움 로컬 환경·읽기 전용 근거 검증 안내

- 작성: 2026-09-24
- 대상: 지정 Windows 11 PC의 CherryPulse-KR-01, 국내 주식 키움 OpenAPI+
- 범위: 현재 저장소에서 실행 가능한 **주문 없는 환경·가상 엔진 검사**와,
  향후 로그인·조회 전 준비할 증거 목록. 이 문서는 주문 실행 허가서가 아니다.

## 1. 먼저 구분할 두 단계

| 단계 | 현재 실행 가능 여부 | 무엇을 확인하는가 |
|---|---|---|
| A. 오프라인 검증 | 가능 | Python 3.10 32비트, 패키지, COM 생성·해제, 원장 테스트 |
| B. 키움 로그인·읽기 전용 조회 | 현재 신규 수집기 없음 | 지정 계좌의 실제 조회 원문, 식별자·페이지·시각·잔고 근거. 조회 도구와 호출 범위 확정 뒤 수행 |

현재 활성 `execution/`은 가상 dispatcher다. 기존 `back/`의 실행 파일,
`main_live.py`나 주문·취소 함수는 검증용으로 실행하지 않는다. 기존 운영 DB를
복사·수정하거나 모의 계좌라도 주문 API를 호출하지 않는다.

## 2. 단계 A: PC에서 바로 실행할 명령

PowerShell에서 프로젝트 루트로 이동한다. 이미 체크아웃한 위치에서
`git status --short`를 먼저 확인한다. 변경 파일이 보이면 덮어쓰지 말고
상태만 기록한다. 작업 트리가 깨끗할 때만 최신 `main`을 빨리 감기로 받는다.

```powershell
git status --short
git branch --show-current
git pull --ff-only origin main
```

브랜치가 `main`이 아니거나 변경 파일이 있으면 위 `git pull`을 생략하고
상태를 공유한다. 아래 명령은 `.venv`와 `.tools`가 이미 구성된 PC 기준이다.
환경이 없으면 [개발 환경](DEVELOPMENT-ENVIRONMENT.md)의 재구성 절부터
진행한다. 터미널에 계좌·토큰·`.env` 내용을 출력하지 않는다.

```powershell
& .\.venv\Scripts\python.exe -I -B -c 'import sys,struct,importlib.metadata as m; from PyQt5.QtWidgets import QApplication; from PyQt5.QAxContainer import QAxWidget; print(sys.version.split()[0],struct.calcsize("P")*8,sys.prefix!=sys.base_prefix); print(m.version("PyQt5"),m.version("PyQt5-Qt5"),m.version("PyQt5-sip")); app=QApplication([]); control=QAxWidget(); ok=control.setControl("KHOPENAPI.KHOpenAPICtrl.1"); print("control_created",ok,"is_null",control.isNull()); control.clear(); print("control_released",control.isNull()); raise SystemExit(0 if ok and struct.calcsize("P")==4 and sys.prefix!=sys.base_prefix else 1)'
& .\.tools\uv\uv.exe pip check --python .venv\Scripts\python.exe --cache-dir .uv-cache
& .\.venv\Scripts\ruff.exe check execution tests
& .\.venv\Scripts\ruff.exe format --check execution tests
$ledgerTestTemp = Join-Path '.tools' ('pytest-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -m pytest -q --tb=line --basetemp $ledgerTestTemp
& .\.venv\Scripts\python.exe -m execution
```

각 명령의 종료 코드와 성공/실패 요약만 기록한다. `ruff format --check`는
파일을 수정하지 않는다. `.tools`의 타입 검사기가 이미 준비된 경우에는
추가로 다음을 실행한다.

```powershell
& node .tools/typecheck/basedpyright/index.js --pythonpath .venv/Scripts/python.exe
```

COM 생성 성공은 서버 로그인·조회·주문 가능성을 보증하지 않는다.
검사 실패 시 오류의 해당 줄과 명령 이름, Python 버전·비트 수를 전달한다.
환경변수 전체, 계좌번호, 비밀번호, 인증서 화면은 전달하지 않는다.

## 3. 단계 B: 로그인·조회 자료 수집 전 확인

현재 저장소에는 **새 원장과 연결된 키움 읽기 전용 수집기**가 없다.
따라서 이 안내서만 보고 조회 스크립트를 임의로 실행할 수 없다. 먼저
지정 PC와 계좌의 환경(모의/실전), 설치 OCX·KOA Studio 버전, 조회 도구와
호출할 TR, 수집 시각·페이지 종료 조건, 결과 보관 위치를 확정한다.
실제/모의 `SendOrder`, 정정, 취소는 별도 범위와 승인 전 실행하지 않는다.

조회 도구가 준비되면 원문은 해당 PC의 접근 제한된 별도 폴더에 보관한다.
각 수집 건에는 수집 시각과 시간대, 계좌/환경을 구분하는 **비밀이 아닌
별칭**, TR·이벤트 이름, 요청 조건, 페이지 번호와 연속조회 종료 여부,
원본 필드/값, 설치 버전, 로컬 수신 순서를 보존한다. 원문을 임의로
체결 사실이나 취소 완료로 바꾸지 않는다. Git에는 원문, 계좌번호,
개인정보, 비밀번호, 토큰, 운영 DB를 올리지 않는다. 공유용 사본에는
민감값을 가리되 동일 주문과 체결 간 비교가 가능하도록 일관된 별칭을 쓴다.

| 우선순위 | 질문 | 필요한 근거 | 현재 허용 범위 |
|---|---|---|---|
| 1 | Q07 조회 완전성 | 미체결·체결·잔고 조회의 페이지, 수집 구간, 연속조회 끝, 누락·지연 | 읽기 전용 수집기 준비 후 |
| 2 | Q01·Q02·Q08 식별자 | 주문·원주문·체결번호, 접수·체결 이벤트와 조회의 연결 | 기존 이력·읽기 전용 자료로 확인 가능한 범위부터 |
| 3 | Q06·Q11 보유 인계 | 조회 보유·매매가능수량·미체결과 원장 관리분의 구분 | 수집만; 자동 편입·청산 금지 |
| 4 | Q03·Q04·Q05·Q10 효과/오류/세션 | 정정·취소·전송 오류의 실제 의미와 주문 가능 시간 | 문서·기존 허용 이력부터; 신규 주문 시험은 별도 결정 |
| 5 | Q09 실행 소유 | Windows 사용자 세션·프로세스 잠금·다른 PC 운영 여부 | 가상 잠금 시험, 실제 계좌 단일 운영 확인은 별도 |

전체 판정 기준은 [Q01~Q13 목록](REBUILD-02-OPEN-QUESTIONS.md)을 따른다.
조회에 결과가 없다는 사실만으로 주문 미전송, 취소 완료 또는 잔고 0을
확정하지 않는다. 실제 조회 화면만 있는 경우 날짜/시각·조회조건·마지막
페이지가 보이도록 기록하되 민감값은 공유 전 가린다.

## 4. 결과 전달 양식

아래 블록을 복사해 채우면 된다. 미수행·미확인은 그대로 쓴다. 출력
전체 대신 실패 명령의 관련 오류 부분만 보내고, 키움 원문은 로컬에
보관한 뒤 가린 사본만 공유한다.

```text
기준 브랜치/커밋: [기입]
작업 트리 상태(깨끗함/변경 파일 있음): [기입]
Windows / Python 버전·비트 수: [기입]
PyQt5·Qt·SIP / OCX·KOA Studio 버전: [기입]
COM 생성·해제: 성공/실패/미실행
pip check / Ruff check / Ruff format check: 각 종료 코드
pytest: 통과·실패 개수 및 종료 코드
python -m execution / basedpyright: 각 종료 코드 또는 미실행
키움 로그인·조회: 미실행 또는 승인된 읽기 전용 수집 범위
Q01~Q13 증거: 질문 ID별 확보/부분/미확인, 별칭 자료 위치
실제·모의 주문/정정/취소 호출: 없음 또는 별도 승인 내용
민감정보 제거 후 공유할 오류·질문: [기입]
```

단계 A 결과는 Windows 개발 검증이며 단계 B의 키움 실증을 대신하지
않는다. 결과를 받으면 질문별로 원문과 정규화 규칙을 대조하고, 불명확한
값은 `UNKNOWN` 또는 격리 상태로 유지한 뒤 필요한 어댑터를 구현한다.
