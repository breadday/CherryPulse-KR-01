# 키움 로컬 검증 결과 — 2026-09-25

## 범위와 안전 경계

- 저장소: `breadday/CherryPulse-KR-01`
- 브랜치: `main`
- 기준 커밋: `ca790c23f5164d978c33ee25cad132de12501183`
- 시작 상태: `git status --short --branch` 결과 `main...origin/main`, 변경 파일 없음
- 실제 주문 API: 호출하지 않음
- `SendOrder`, 정정, 취소: 호출하지 않음
- `CommConnect`, 계좌 선택, 계좌/TR 조회: 호출하지 않음
- 운영 SQLite: 열람·변경하지 않음
- `.env`, 계좌번호, 비밀번호, 토큰, 인증서: 출력·보관·커밋하지 않음

## 단계 A 실행 결과

| 검사 | 명령 요약 | 결과 |
|---|---|---|
| Python 격리 환경 | `.venv\Scripts\python.exe -I -B` 버전·비트수 | Python 3.10.8, 32비트, 격리됨 |
| PyQt5 패키지 | PyQt5 / Qt / SIP 버전 출력 | 5.15.11 / 5.15.2 / 12.18.0 |
| 의존성 | `python -m pip check` | 통과, 종료 코드 0 (Python310-32 사용자 설치 패키지) |
| Ruff check | `python -m ruff check execution tests verify_kiwoom_com.py` | 통과, 종료 코드 0 |
| Ruff format | `python -m ruff format --check execution tests verify_kiwoom_com.py` | 41개 파일 포맷 확인, 종료 코드 0 |
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

수정 사항은 환경 검증과 COM 검증을 분리한 `verify_kiwoom_com.py` 추가 및 안내
명령 변경이다. 로그인·계좌 조회·주문 경계에는 변경이 없다.

## 단계 B 읽기 전용 경계

다음 코드를 추가했다.

- `adapters/kiwoom_readonly.py`
- `adapters/__init__.py`
- `tests/test_kiwoom_readonly.py`

경계의 특징:

- `execution`을 import하지 않고 로컬 실행 원장을 열지 않는다.
- 연결 상태는 `GetConnectState()` 관측값으로만 기록한다. 로그인·계좌 인증 성공으로 승격하지 않는다.
- 읽기 전용 후보 TR만 허용한다: `opw00018` 보유, `opt10075` 미체결, `opw00007` 체결 이력 후보.
- `SendOrder`와 정정·취소 TR은 화이트리스트에 없으므로 거절한다.
- 요청 조건, TR, 수신 시각, 페이지 번호, `prev_next`, 완료 여부, 오류, 원문 payload를 별도 capture 구조로 보존할 수 있다.
- 계좌번호·비밀번호 입력값은 capture에 `<redacted>`로 보존한다. 실제 원문은 이 저장소에 저장하지 않는다.
- 페이지 누락·중복·오류·미완료·연속조회 잔여는 `QUARANTINED`, 응답 미완료는 `UNKNOWN`이다.
- 완전한 조회도 `READ_ONLY_QUERY_COMPLETE_NOT_MANAGED`로 표시하며 관리 보유·가상 체결로 편입하지 않는다.

이번 단계에서는 연결 상태가 `0`이므로 실제 TR 응답 capture를 수집하지 못했다.
따라서 위 TR과 필드 목록은 기존 공식 문서·설치 자료·보관 코드에서 확인한
후보 경계이며, 설치된 KOA Studio의 실제 응답 의미를 검증한 것이 아니다.

## Q01~Q11 상태

| 항목 | 이번 결과 | 판정 |
|---|---|---|
| Q01 주문번호 범위·정정 연결 | 실제 응답 없음. 필드 존재만 기존 문서에서 확인 | 미확인, 주문 활성화 차단 |
| Q02 체결번호 유일성·중복 | 실제 체결 자료 없음 | 미확인, 체결 편입 차단 |
| Q03 정정 수량 의미 | 주문 호출 금지로 자료 없음 | 미확인, 정정 어댑터 차단 |
| Q04 취소 접수·완료·지연 체결 | 실제 자료 없음 | 미확인, ACK만으로 예약 해제 금지 |
| Q05 전송 오류의 미전송 근거 | 가상 검사는 있으나 키움 반환값 검증 없음 | 부분 확인, UNKNOWN 자동 재전송 금지 |
| Q06 매매가능수량·예약 반영 | `매매가능수량` 필드 후보만 확인 | 미확인, 여력 계산 차단 |
| Q07 조회 페이지 완전성 | capture 모델과 가상 누락 검사는 추가했으나 실제 응답 없음 | 부분 확인, 실제 복구 차단 |
| Q08 접수 전 체결 연결 | 실제 이벤트 없음. 가상 역순 검사는 기존 테스트 | 부분 확인, 실제 연결 차단 |
| Q09 단일 PC 실행 잠금 | 기존 가상 잠금 검사는 통과. 키움 계좌 운영 정책은 미확인 | 부분 확인 |
| Q10 Python/Qt/OCX | Python·PyQt5 버전·32비트·OCX 등록/경로·`setControl`/`clear` 확인, `GetConnectState=0` | 부분 확인, 실제 주문 경계 차단 |
| Q11 기존 보유·수동 거래 배정 | 운영 DB와 계좌 조회를 보지 않음 | 미확인, 자동 편입·청산 금지 |

### 자료 별칭

- 공식 문서: `KIWOOM-OPENAPI-DEVGUIDE-V1.7`
- 설치 환경 자료: `LOCAL-OCX-ENV-2026-09-14`
- 이번 검증의 가상 capture: `TEST-READONLY-CAPTURE-2026-09-25`
- 실제 원문 보관 위치: **수집하지 않음**

## 단계 C 가상 안전성

읽기 전용 정규화 경계의 별도 테스트 7개가 이전 커밋 검증에서 통과했다. 확인한 내용은 다음과 같다.

- 완전한 페이지는 공백만 정규화하고 원문 payload·조회 근거를 별도 유지
- 페이지 누락·중복·오류·미완료는 정상 snapshot으로 변환하지 않음
- 체결 이력 후보에 주문번호·체결번호를 임의 생성하지 않음
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
