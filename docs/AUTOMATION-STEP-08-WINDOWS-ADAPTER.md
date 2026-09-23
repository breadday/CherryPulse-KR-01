# STEP 08 — Windows 모의환경 어댑터 경계

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-22 |
| 작업 브랜치 | `feat/automated-rebuild-20260921` |
| 실행 범위 | Windows/PAPER 선언 검증, 조회 전용 quote, 결정적 submit 결과, UNKNOWN·부분체결 경계 |
| 안전 경계 | 실제 Windows COM·키움·네트워크·계좌·주문 호출 없음 |

이번 단계는 실제 키움 API를 연결하지 않고, Windows 모의환경에 연결될 adapter의 안전한 계약을 고정한다. 실행 환경이 Linux라도 대상 플랫폼과 PAPER 환경을 명시적으로 선언해야 하며, 구현은 deterministic scripted adapter로 제한한다.

## 구현 범위

- `WindowsAdapterConfig`는 `target_os=WINDOWS`, `environment=PAPER`만 허용한다.
- `AdapterRequest`는 operation ID·종목·방향·양을 엄격히 검증한다.
- `quote()`는 설정된 조회 데이터만 반환하며 transport call을 만들지 않는다.
- `submit()`은 ACK, REJECT, TIMEOUT, PARTIAL 결과를 명시적 관측 상태로 변환한다.
- 동일 operation ID는 기존 관측을 재생한다.
- UNKNOWN 관측은 자동 재전송하지 않고 `RETRY_BLOCKED_UNKNOWN`으로 차단한다.
- 부분체결은 요청 수량의 일부를 명시하며 broker order ID를 보존한다.
- REJECTED 결과에는 broker order ID를 만들지 않는다.

## 제외 범위

- Windows COM, 키움 OpenAPI+, 로그인, 인증서, 토큰을 연결하지 않는다.
- HTTP, WebSocket, 외부 DB, Vercel, 관리형 서비스에 연결하지 않는다.
- 실계좌·모의계좌 주문을 제출하지 않는다.
- timeout을 성공·미전송으로 추정하지 않는다.
- UNKNOWN을 자동 재주문하지 않는다.

## 변경 파일

- `verification/windows_adapter.py`: 결정적 Windows/PAPER adapter 경계
- `tests/test_windows_adapter.py`: 환경·조회·ACK·REJECT·UNKNOWN·부분체결·malformed 입력 테스트
- `docs/AUTOMATION-DEVELOPMENT-PLAN.md`: STEP 08 상태 기록
- `README.md`: 단계 문서 링크

## RED → GREEN 근거

### RED

신규 테스트에서 `verification.windows_adapter`가 존재하지 않아 `ModuleNotFoundError`가 발생했다. 구현 후 malformed operation ID와 비문자 side 입력의 통제된 거절을 추가로 검증했고, 수정 전 해당 테스트가 실패했다.

### GREEN

결정적 scripted adapter를 추가한 뒤 특정 테스트 7개가 통과했다. quote는 transport 호출 없이 반환되며, UNKNOWN은 재전송되지 않고, 부분체결과 REJECTED가 서로 다른 명시적 관측으로 보존된다.

## 자동검사 결과

```text
PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q tests/test_windows_adapter.py
7 passed in 0.39s

PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q
159 passed in 7.10s

python3 -m py_compile verification/windows_adapter.py tests/test_windows_adapter.py
passed

git diff --check
passed
```

## 보안·운영 경계

- 이 adapter는 이름상 Windows 대상이지만 현재 Linux 검증 환경에서만 실행되는 로컬 paper 시뮬레이터다.
- `WINDOWS/PAPER` 선언은 실제 키움 연결이나 모의계좌 인증을 의미하지 않는다.
- 관측 상태는 외부 broker 사실이 아니며, 실제 adapter 구현 때 공식 API 반환값과 증거 규칙을 별도로 확인해야 한다.
- UNKNOWN은 안전한 재conciliation 대상으로 남기며 주문 재전송을 허용하지 않는다.

## 독립 검토

staged diff와 최종 자동검사 결과를 기준으로 독립 fail-closed reviewer를 수행한다. 결함이 발견되면 RED 회귀 테스트를 먼저 추가하고 수정 후 새 staged diff를 재검토한다.

## 완료 조건

- 특정 테스트와 전체 Python 회귀가 통과한다.
- 문법 검사와 staged diff 검사가 통과한다.
- 독립 reviewer가 `passed: true`를 반환한다.
- 문서의 테스트 수가 최종 실행 결과와 일치한다.
- 커밋과 원격 SHA를 읽어 검증한다.
