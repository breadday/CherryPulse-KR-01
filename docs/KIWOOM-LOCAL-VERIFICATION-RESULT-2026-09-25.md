# 키움 로컬 검증 결과 — 2026-09-25

## 최신 main 이벤트 연결 재검증 — 2026-09-25

읽기 전용 수집기의 `OnReceiveMsg`·`OnReceiveTrData`는 이제 화면번호,
요청명, TR 코드가 진행 중인 단일 요청과 일치하는 이벤트만 기록한다.
다른 화면·요청·TR의 메시지가 현재 조회의 실패 사유로 들어오거나 다른
페이지가 이어붙는 것을 막는다. 필수 식별 인자가 없는 이벤트도 기록하지
않고 응답을 기다리거나 시간 초과로 남긴다. 이는 실제 키움 이벤트의
식별자 수신 형식이 설치 버전에서 일치하는지 검증한 결과는 아니다.

원격 변경을 통합하기 전 기준은 `main`의 `e9cac65ade37ec494323d5a53b299c47a6db8f45`이며 작업
트리는 검사 전 깨끗했다. 이벤트 연결 검증을 보강한 뒤 Python 3.10.8 32비트에서
다음 검사를 다시 실행했다.

| 검사 | 종료 코드 | 결과 |
|---|---:|---|
| `py -3.10-32 -c "...version/bits..."` | 0 | Python 3.10.8, 32비트 |
| `py -3.10-32 -m pytest -q --tb=line --basetemp .tools\\pytest-current` | 0 | 149 passed |
| `py -3.10-32 -m ruff check .` | 0 | 통과 |
| `py -3.10-32 -m ruff format --check .` | 0 | 79 files already formatted |
| `py -3.10-32 -m execution` | 0 | 가상 데모 정상 출력 |
| `git diff --check` | 0 | 통과 |

추가한 이벤트 검증은 화면번호·요청명·TR 코드가 요청과 다르면
`TR_EVENT_MISMATCH`로 격리하고 `GetRepeatCnt` 또는 다음 페이지 요청을 하지
않도록 한다. 불일치 각 항목과 일치 경로를 테스트했다.

실제 조회는 `py -3.10-32 verify_kiwoom_readonly.py --tr opt10075 --timeout 120`로
실행했다. 사용자가 계좌를 직접 선택했고, `CommRqData` 반환값은 0이었다. 민감한
입력값과 증권사 원문 메시지는 저장·기록하지 않고 종류만 `QUERY`로 남겼다.

```text
tr opt10075
alias READONLY-ACCOUNT-1
page=1 screen=9102 request_name=readonly_opt10075 tr_code=opt10075
event_match=True record_name=<empty> prev_next=<empty> row_count=0 complete=True
page_complete=True content_validity=NOT_VALIDATED error=BROKER_MESSAGE_PRESENT
```

화면번호·요청명·TR 코드가 모두 일치했으며 실제 다중 페이지는 발생하지 않았다.
행 수 0은 미체결 0건이나 취소 완료를 확정하지 않으며 원장에 편입하지 않았다.
이번 실행에서 호출한 실제 TR은 `opt10075` 하나뿐이고 `opw00007` 및 주문 API는
호출하지 않았다.

## 후속 검증: 다중 페이지 완료 판정

읽기 전용 실행 경로는 앞 페이지의 연속조회 표식 `2`와 마지막 페이지의
종료 표식 `0` 또는 빈 값이 차례대로 수신돼야 `page_complete=True`로
표시한다. 첫 페이지가 종료됐는데 추가 페이지가 오거나, 마지막 페이지가
빠지거나, 알 수 없는 표식이 오면 완료 처리하지 않는다. 공용 capture의
`COMPLETE` 판정도 같은 표식 순서를 확인하도록 맞췄다. 내용 유효성은
이 페이지 판정과 별개이며 관리 보유·체결로 자동 편입하지 않는다.

이전 기록의 Linux Python 3.12 분리 환경 관련 pytest **15 passed**와 구별해,
이번 Windows Python 3.10 32비트 전체 검사는 **145 passed**였다. 실제 키움
다중 페이지 수신은 이번 재실행에서도 확인하지 못했다.

## 후속 안전 경계: 미검증 TR 차단

`opw00007`의 출력 필드와 연속조회 규격을 확인하지 못한 상태인데 공용
`QuerySpec` 허용 목록에 남아 있어 코드와 아래의 보류 판정이 달랐다.
어댑터 허용 목록에서 제외하고 생성 단계의 거절을 시험했다. 로컬 Linux
Python 3.12 분리 환경의 관련 pytest **7 passed**, Ruff 검사·포맷 검사,
`git diff --check` 통과. 이는 지정 Windows PC의 137개 전체 검사나
키움 재조회가 아니다. Windows 전체 검사는 최신 커밋을 받은 뒤 재실행해야
하며 `opw00007`은 규격 검증 전까지 보류한다.

## 범위와 안전 경계

- 저장소: `breadday/CherryPulse-KR-01`
- 브랜치: `main`
- 기준 커밋: `ca790c23f5164d978c33ee25cad132de12501183`
- 시작 상태: `git status --short --branch` 결과 `main...origin/main`, 변경 파일 없음
- 실제 주문 API: 호출하지 않음
- `SendOrder`, 정정, 취소: 호출하지 않음
- `CommConnect`: 로그인 창을 통한 연결 확인에서 호출함
- 계좌 선택: 사용자 직접 처리
- 읽기 전용 `opw00018`, `opt10075`: 각각 독립 호출
- 운영 SQLite: 열람·변경하지 않음
- `.env`, 계좌번호, 비밀번호, 토큰, 인증서: 출력·보관·커밋하지 않음

## 단계 A 실행 결과

| 검사 | 명령 요약 | 결과 |
|---|---|---|
| Python 격리 환경 | `.venv\Scripts\python.exe -I -B` 버전·비트수 | Python 3.10.8, 32비트, 격리됨 |
| PyQt5 패키지 | PyQt5 / Qt / SIP 버전 출력 | 5.15.11 / 5.15.2 / 12.18.0 |
| 의존성 | `python -m pip check` | 통과, 종료 코드 0 (Python310-32 사용자 설치 패키지) |
| Ruff check | `python -m ruff check execution tests verify_kiwoom_com.py verify_kiwoom_connection.py verify_kiwoom_readonly.py` | 통과, 종료 코드 0 |
| Ruff format | `python -m ruff format --check execution tests verify_kiwoom_com.py verify_kiwoom_connection.py verify_kiwoom_readonly.py` | 43개 파일 포맷 확인, 종료 코드 0 |
| 전체 pytest | `python -m pytest -q --tb=line --basetemp .tools\pytest-current` | **137 passed**, 종료 코드 0 |
| 가상 데모 | `python -m execution` | 정상 출력, 종료 코드 0 |

참고로 선택 검사인 `basedpyright`는 종료 코드 1이다. 기존 Pydantic 입력 경계가
런타임에서 문자열을 검증·변환하지만 정적 생성자 타입은 `Decimal`로 선언된
불일치가 대부분이며, 기존 코드·테스트에서 54건이 보고됐다. 이번 읽기 전용
경계의 오류는 별도로 추가되지 않았다. 타입 선언을 임의로 바꾸어 거래 경계를
변경하지 않고 후속 작업으로 남긴다.

초기에는 프로젝트 `.venv`/uv가 없고 3.10 패키지가 없어 재검사가 불가능했지만,
운영 소스와 분리된 사용자 개발 패키지로 동일한 32비트 Python 3.10.8에
`pydantic`, pytest, Ruff를 설치한 뒤 재검사했다. Python 3.8 전역 pytest는
`typing.Annotated` 부재로 부적합했고 사용하지 않았다. 현재 저장소 기준으로
요청된 **137개 테스트와 Ruff는 통과**했다.

### COM 결과

현재 PC에는 문서에 기록된 프로젝트 `.venv`가 존재하지 않았다. 설치된
`Python310-32\python.exe`를 사용해 동일한 검사와 COM-only 최소 재현을 각각
별도 프로세스에서 실행했다. Python·PyQt5 버전과 COM 등록 상태는 다음과 같다.

```text
3.10.8 32 False
5.15.11 5.15.2 12.18.0
control_created True is_null False
control_released True
```

기존 인라인 검사와 COM-only 최소 재현 모두 `setControl()` 및 `clear()`까지
정상 완료했다. 기존 inline 종료식은 COM 결과뿐 아니라 가상환경 여부도 성공
조건으로 검사했으므로, 현재 직접 설치 Python에서는 COM 성공 후 종료 코드 1이
될 수 있었다. 이를 `verify_kiwoom_com.py`로 분리했고 COM 성공 판정은 32비트,
생성 성공, 해제 성공만 사용한다.

레지스트리 조회 결과는 `HKCR\KHOPENAPI.KHOpenAPICtrl.1` →
`{A1574A0D-6BFA-4BD7-9020-DED88711818D}` →
`HKCR\WOW6432Node\CLSID\...\InprocServer32` →
`C:\OpenAPI\KHOpenAPI.ocx`로 일치했다. OCX 파일은 존재하며 파일 버전은
`1.0.0.1`이다. 이는 32비트 등록·경로가 현재 검사 환경과 일치함을 뜻하지만,
OCX 내부 안정성이나 서버 연결을 보증하지 않는다.

이전 `0xC0000409` 기록도 이벤트 로그에서 재대조했다. 해당 기간의 Application
Error Event 1000 오류 모듈은 `NVDisplay.Container.exe`였고, 키움 OCX·Python
프로세스 이벤트가 아니었다. 따라서 예외 코드만으로 키움 COM 충돌 원인을
단정하지 않으며, 이번 재현에서는 키움 COM 충돌이 재현되지 않았다.

따라서 이번 실행은 다음으로 판정한다.

- COM 생성·해제: **성공**
- 키움 로그인: 미실행
- 국내 주식 계좌 조회: 미실행
- 주문 가능성: 판단하지 않음

### 단계 B-0 연결 상태 확인 — 2026-09-25

COM 생성 직후 별도 프로세스에서 `GetConnectState()`만 한 번 호출했다.

```text
observed_at 2026-09-25T02:50:56.601424+00:00
control_created True connect_state 0 connected False
process_exit 0
```

재확인도 별도 프로세스에서 같은 결과였다.

```text
observed_at 2026-09-25T02:56:26.121921+00:00
control_created True connect_state 0 connected False
process_exit 0
```

### 단계 B-1 수동 로그인 경로 — 2026-09-25

읽기 전용 실행 경로 `verify_kiwoom_readonly.py --tr opw00018`를 실행했다.
로그인 이벤트와 연결 상태는 성공했지만, 계좌 선택 단계에서 중단되어 TR은
호출하지 않았다.

```text
login_status LOGIN_EVENT login_error 0 connected True
account_count 1
TR request: not called
```

첫 실행은 표준입력이 없는 실행 채널에서 계좌 선택을 기다리다 `EOFError`로
종료되었다. GUI 대화상자로 변경한 재실행도 계좌 선택 대화상자에서 사용자
입력을 기다리며 실행 채널 제한시간을 초과했다. 계좌를 임의 선택하거나
비밀번호를 추정하지 않았고, 입력 전 `CommRqData`는 호출되지 않았다.

지정 PC의 사용자 데스크톱에서 일반 PowerShell을 열어 아래 명령을 실행하면
로그인 창과 계좌 선택·비밀번호 입력 대화상자를 직접 처리할 수 있다.

```powershell
py -3.10-32 verify_kiwoom_readonly.py --tr opw00018 --timeout 180
```

계좌 선택과 비밀번호 입력이 완료되면 출력되는 요청·응답 시각과 페이지
메타데이터만 공유한다. 계좌번호·비밀번호·원문 응답은 공유하지 않는다.

### 단계 B-2 `opw00018` 메시지 원인 조사 시도 — 2026-09-25

`opw00018`만 대상으로 안전 메타데이터 probe를 사용자 데스크톱 프로세스로
실행했다. 로그인 대기 제한시간에 도달해 계좌 입력 단계로 진행하지 못했다.

```text
login_status LOGIN_TIMEOUT login_error None connected False
TR: opw00018 (not called)
SetInputValue: not called
CommRqData return: not available
OnReceiveMsg: not received
```

따라서 이번 시도에서는 `BROKER_MESSAGE_PRESENT`의 종류·시각·가린 메시지,
요청 입력 항목, TR 반환 코드를 확인할 자료가 없다. 이는 조회 결과가 비어
있다는 뜻이 아니며, 보유 0건으로 기록하지 않는다. `page_complete`나 조회
내용 유효성도 판정하지 않는다.

비밀번호 입력이 필요한 실제 조사는 지정 PC의 사용자 데스크톱에서 아래
명령을 실행한 뒤, 로그인 창·계좌 선택·비밀번호 대화상자를 직접 처리해야
한다. 입력 전에는 `CommRqData`가 호출되지 않는다.

```powershell
py -3.10-32 verify_kiwoom_readonly.py --tr opw00018 --timeout 180
```

출력에서 `input_fields`, `request_return`, `broker_messages`, `pages`,
`page_complete`, `content_validity`만 공유한다. 계좌번호·비밀번호·원문
응답은 공유하지 않는다.

- COM 생성: 성공
- 연결 상태: `0` / 미연결
- COM 해제: 성공
- `CommConnect`, 계좌번호·비밀번호 입력, 계좌 선택, `CommRqData`: 미호출
- 이번 단계에서 호출한 TR: 없음

따라서 `opw00018`, `opt10075`, `opw00007` 조회는 보류했다. 사용자가 지정 PC에서
키움 OpenAPI+ 로그인 화면을 직접 열고, 필요한 로그인·인증·계좌 선택을 직접
수행해야 한다. 계좌번호·비밀번호·인증 화면을 이 저장소나 채팅에 공유하지
않는다. 로그인 완료 후에는 먼저 동일한 `GetConnectState()`를 다시 확인하고,
`1`이 확인된 경우에만 허용된 계좌를 사용해 한 종류씩 읽기 전용 TR을 요청한다.
로그인 화면에서 추가 인증이나 계좌 선택이 필요한 경우 자동 입력하지 않고
사용자 조작을 기다린다.

수정 사항은 환경 검증과 COM 검증을 분리한 probe 및 단일 TR 메타데이터
수집 경로다. 로그인·읽기 전용 조회 외 주문 경계에는 변경이 없다.

### 단계 B-3 성공한 `opw00018` PowerShell 실행 — 2026-09-25

사용자가 지정 PC 화면에서 계좌 선택과 비밀번호 입력을 직접 처리한 성공
실행의 안전 메타데이터다. 계좌번호·비밀번호와 원문 응답은 보관하지 않았다.

```text
login_status LOGIN_EVENT login_error 0 connected True
tr opw00018 alias READONLY-ACCOUNT-1
requested_at 2026-09-25T03:57:07.120621+00:00
broker_message_at 2026-09-25T03:57:07.138625+00:00
responded_at 2026-09-25T03:57:07.140631+00:00
request_return 0
input_fields 계좌번호=<redacted>, 비밀번호=<redacted>, 비밀번호입력매체구분=00, 조회구분=1
pages page=1 prev_next=<empty> row_count=0 complete=True
page_complete True
content_validity NOT_VALIDATED
broker_message_kind PAPER_TRADING_NO_QUERY_HISTORY
error BROKER_MESSAGE_PRESENT
```

가린 증권사 메시지는 사용자가 지정한 기준에 따라 `모의투자 조회 내역 없음`으로
분류했다. 이는 모의투자 계좌에 해당 조회 내역이 없다는 메시지 분류일 뿐,
보유 수량 0이나 보유 없음의 확정이 아니다. `row_count=0`과
`page_complete=True`도 응답 페이지의 완전성만 나타내며, 보유 데이터 의미의
유효성은 `NOT_VALIDATED`로 남겼다.

### 단계 B-4 독립 `opt10075` 읽기 전용 실행 — 2026-09-25

`opw00018`과 별도 프로세스에서 `opt10075`만 요청했다. 사용자가 계좌를 직접
선택했으며 비밀번호 입력은 요구되지 않았다.

```text
login_status LOGIN_EVENT login_error 0 connected True
tr opt10075 alias READONLY-ACCOUNT-1
requested_at 2026-09-25T03:55:50.821099+00:00
broker_message_at 2026-09-25T03:55:50.920954+00:00
responded_at 2026-09-25T03:55:50.936959+00:00
request_return 0
input_fields 계좌번호=<redacted>, 전체종목구분=0, 매매구분=0, 종목코드=<empty>, 체결구분=1
pages page=1 prev_next=<empty> row_count=0 complete=True
page_complete True
content_validity NOT_VALIDATED
broker_message_kind QUERY_COMPLETED
error BROKER_MESSAGE_PRESENT
```

가린 메시지는 일반 조회 완료 메시지로 분류되었다. 따라서 `row_count=0`은
미체결 없음·미전송·취소 완료를 확정하지 않으며, 실제 미체결 의미의 유효성은
검증하지 않았다. 연속조회 표식은 `<empty>`로 종료되어 페이지 완전성은
확인했지만 내용 승격은 하지 않았다.

### 설치 TR 규격·필드 대조

설치 자료는 다음 암호화 파일의 존재와 메타데이터만 확인했다. 파일 내용이나
원문 응답은 저장소에 복사하지 않았다.

```text
C:\OpenAPI\data\opw00018.enc  size=682  modified=2025-03-01T21:37:02+09:00
C:\OpenAPI\data\opt10075.enc  size=660  modified=2025-03-01T21:37:02+09:00
C:\OpenAPI\data\opw00007.enc  size=633  modified=2025-03-01T21:37:02+09:00
```

설치 암호화 자료를 임의 해독하지 않고, 공식 가이드의 조회 API 구조와 보관
코드의 후보 매핑을 대조했다. `opw00018` 입력은 계좌번호·비밀번호·비밀번호
입력매체구분·조회구분이며 후보 응답 필드는 종목번호·종목명·보유수량·매매가능수량·
매입가·현재가다. `opt10075` 입력은 계좌번호·전체종목구분·매매구분·종목코드·
체결구분이며 후보 응답 필드는 주문번호·종목코드·종목명·주문구분·주문가격·
주문수량·미체결수량·체결량·주문상태다. 이 대조는 필드 후보와 실제 응답
구조의 일치 확인이며, 빈 응답의 업무 의미를 공식적으로 보증하지 않는다.

이번 실제 응답에서 확인된 사실은 `CommRqData` 반환값 0, 수신 시각, 1페이지,
`prev_next` 종료, `GetRepeatCnt` 행 수 0, 메시지 분류뿐이다. 필드 값이 없다는
이유로 보유 0 또는 미체결 0을 원장에 기록하지 않았다.

`opw00007.enc`는 존재하며 KOA Studio 설치 버전 `1.0.0.1`에서 입력 규격의
다음 항목을 확인했다. 실제 값은 기록하지 않았다.

```text
주문일자
계좌번호=<redacted>
비밀번호=<unused>
비밀번호입력매체구분=00
조회구분=1|2|3|4
주식채권구분=0|1|2
매도수구분=0|1|2
종목코드=<optional>
시작주문번호=<optional>
거래소구분=%|KRX|NXT|SOR|<empty means all>
```

확인 자료에는 `opw00007`의 출력 필드 목록과 실제 연속조회 종료 조건
(`sPrevNext`/다음 페이지 조건)이 포함되어 있지 않았다. 설치 암호화 자료를
임의 해독하거나 입력 규격만으로 출력 필드를 추정하지 않는다. 공식 자료의
체결번호 관련 FID 존재만으로 `opw00007` TR 규격이나 빈 결과의 의미를
확정할 수 없다. 따라서 `opw00007`은 출력·연속조회 규격 미확인으로 계속
보류했으며 `CommRqData`를 호출하지 않았다.

### 세 TR 증거 요약

| TR | 규격 상태 | 실행·반환 | 메시지·페이지 | 내용 유효성·판정 |
|---|---|---|---|---|
| `opw00018` | 설치 입력 후보·응답 후보와 보관 코드 대조 | 실행, `return=0` | 가린 메시지 `모의투자 조회 내역 없음`; 1페이지, `prev_next=<empty>`, `complete=True` | `NOT_VALIDATED`; 보유 0 확정 안 함 |
| `opt10075` | 설치 입력 후보·응답 후보와 보관 코드 대조 | 실행, `return=0` | 가린 일반 조회 완료 메시지; 1페이지, `prev_next=<empty>`, `complete=True` | `NOT_VALIDATED`; 미체결 0 확정 안 함 |
| `opw00007` | 입력 항목은 KOA Studio 1.0.0.1에서 확인. 출력·연속조회 규격 미확인 | **보류, 호출 안 함** | 메시지·페이지·반환 코드 없음 | `UNKNOWN`; 체결 이력 0 확정 안 함 |

실제 수신 두 TR의 요청·메시지·응답 시각과 모든 수신 페이지 메타데이터는
위의 상세 사례에 기록했다. `opw00007`은 조회 자체가 없으므로 시각·페이지
종료 조건도 기록하지 않고 `NOT_CALLED`로 남겼다.

## 단계 B 읽기 전용 경계

다음 코드를 추가했다.

- `adapters/kiwoom_readonly.py`
- `adapters/__init__.py`
- `tests/test_kiwoom_readonly.py`

경계의 특징:

- `execution`을 import하지 않고 로컬 실행 원장을 열지 않는다.
- 연결 상태는 `GetConnectState()` 관측값으로만 기록한다. 로그인·계좌 인증 성공으로 승격하지 않는다.
- 읽기 전용 후보 TR 중 `opw00018` 보유, `opt10075` 미체결만 허용한다. `opw00007`은 출력·연속조회 규격 확인 전까지 어댑터에서도 차단한다.
- `SendOrder`와 정정·취소 TR은 화이트리스트에 없으므로 거절한다.
- 요청 조건, TR, 수신 시각, 페이지 번호, `prev_next`, 완료 여부, 오류, 원문 payload를 별도 capture 구조로 보존할 수 있다.
- 계좌번호·비밀번호 입력값은 capture에 `<redacted>`로 보존한다. 실제 원문은 이 저장소에 저장하지 않는다.
- 페이지 누락·중복·오류·미완료·연속조회 잔여는 `QUARANTINED`, 응답 미완료는 `UNKNOWN`이다.
- 완전한 조회도 `READ_ONLY_QUERY_COMPLETE_NOT_MANAGED`로 표시하며 관리 보유·가상 체결로 편입하지 않는다.

초기 연결 상태 `0` 단계에서는 실제 TR 응답 capture를 수집하지 못했지만,
이후 수동 로그인 후 `opw00018`과 `opt10075`의 안전 메타데이터를 각각
수집했다. 원문 응답과 민감 입력은 보관하지 않았고, 설치된 KOA Studio의
빈 결과 업무 의미까지 검증한 것은 아니다.

## Q01~Q11 상태

| 항목 | 이번 결과 | 판정 |
|---|---|---|
| Q01 주문번호 범위·정정 연결 | 실제 응답 없음. 필드 존재만 기존 문서에서 확인 | 미확인, 주문 활성화 차단 |
| Q02 체결번호 유일성·중복 | `opw00007` 입력 항목과 공식 FID 존재는 확인. 출력 필드·연속조회·실제 체결 자료 없음 | 미확인, 체결 편입 차단 |
| Q03 정정 수량 의미 | 주문 호출 금지로 자료 없음 | 미확인, 정정 어댑터 차단 |
| Q04 취소 접수·완료·지연 체결 | 실제 자료 없음 | 미확인, ACK만으로 예약 해제 금지 |
| Q05 전송 오류의 미전송 근거 | 가상 검사는 있으나 키움 반환값 검증 없음 | 부분 확인, UNKNOWN 자동 재전송 금지 |
| Q06 매매가능수량·예약 반영 | `opw00018` 입력·후보 필드와 1페이지 종료를 확인. 예약 반영은 자료 없음 | 미확인, 여력 계산 차단 |
| Q07 조회 페이지 완전성 | 두 TR 모두 1페이지·`prev_next` 종료·`page_complete=True` 확인 | 부분 확인, 내용 유효성·실복구 차단 |
| Q08 접수 전 체결 연결 | 실제 이벤트 없음. 가상 역순 검사는 기존 테스트 | 부분 확인, 실제 연결 차단 |
| Q09 단일 PC 실행 잠금 | 기존 가상 잠금 검사는 통과. 키움 계좌 운영 정책은 미확인 | 부분 확인 |
| Q10 Python/Qt/OCX | Python·PyQt5 버전·32비트·OCX 등록/경로·`setControl`/`clear` 확인, 수동 로그인 이벤트와 `GetConnectState=1` 확인 | 부분 확인, 실제 주문 경계 차단 |
| Q11 기존 보유·수동 거래 배정 | 보유 TR을 조회했지만 빈 결과 의미와 관리 배정은 검증하지 않음 | 미확인, 자동 편입·청산 금지 |

### 자료 별칭

- 공식 문서: `KIWOOM-OPENAPI-DEVGUIDE-V1.7`
- 설치 환경 자료: `LOCAL-OCX-ENV-2026-09-14`
- 이번 검증의 가상 capture: `TEST-READONLY-CAPTURE-2026-09-25`
- 실제 원문 보관 위치: **수집하지 않음**

## 단계 C 가상 안전성

읽기 전용 정규화 경계의 별도 테스트 7개가 이전 커밋 검증에서 통과했다. 확인한 내용은 다음과 같다.

- 완전한 페이지는 공백만 정규화하고 원문 payload·조회 근거를 별도 유지
- 페이지 누락·중복·오류·미완료는 정상 snapshot으로 변환하지 않음
- 미검증 체결 이력 후보 TR은 요청 모델 생성 단계에서 차단
- 비허용 TR과 주문 요청 경계를 거절
- 기존 전체 가상 원장 테스트 130개로 역순 체결·부분체결·중복 이벤트·취소 UNKNOWN·재시작 미해결 상태를 재확인
- 기존 원장 정책에 따라 확인 전 예약 해제와 UNKNOWN 자동 재주문을 허용하지 않음

손절 매도 실패·거절을 자동 재주문하지 않는 기존 가상 정책도 유지된다. 실제 키움 오류·조회 원문에 적용한 검증은 아직 아니다.

## 다음 PC 작업과 결정

1. 키움 설치 PC에서 `KHOPENAPI.KHOpenAPICtrl.1`을 수동으로 생성할 수 있는지, OCX 등록·KOA Studio 실행 여부를 확인한다. 이번 예외가 재현되면 예외 화면과 OCX/Qt 설치 버전만 공유하고 계좌정보는 공유하지 않는다.
2. COM 생성이 해결된 뒤에도 먼저 `GetConnectState()`만 읽고, 계좌번호·비밀번호 입력이 필요한 TR은 별도 승인된 읽기 전용 범위로 확정한다.
3. `opw00018`, `opt10075`, `opw00007`의 실제 입력값·필드·페이지 종료 규칙을 KOA Studio와 공식 자료로 대조한다.
4. 읽기 전용 원문은 Git 밖의 접근 제한 폴더에 저장하고 `READONLY-CAPTURE-<alias>-<date>` 별칭만 공유한다.
5. Q01~Q11의 미확인 상태가 해소되기 전에는 실제 주문 어댑터와 계좌 인계를 활성화하지 않는다.
