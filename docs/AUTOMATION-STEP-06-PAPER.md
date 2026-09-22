# STEP 06 — 모의환경 검증 경계

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-22 |
| 작업 브랜치 | `feat/automated-rebuild-20260921` |
| 실행 범위 | 조회 전용 경계, 원문 이벤트 저장·재생, 로컬 paper 주문·취소·부분체결 검사 |
| 안전 경계 | 실계좌·실브로커·실주문·운영 배포 부작용 없음 |

이번 단계는 키움 OpenAPI+에 직접 연결하지 않는다. Windows 모의환경에 연결하기 전에 동일한 안전 경계를 검증하는 결정적 로컬 paper harness만 제공한다.

## 구현 범위

- `ReadOnlyQuoteGateway`가 조회만 허용하고 주문 요청을 `PAPER_READ_ONLY`로 거절한다.
- `RawEventLog`가 원문 이벤트를 append-only로 보관하고 event ID 중복을 제거한다.
- `RawEventLog.replay()`가 저장된 원문 이벤트 순서를 그대로 재생한다.
- `PaperBroker`가 결정적 paper 주문 ID를 발급한다.
- `PaperBroker`가 부분체결 수량·평균 체결가·잔량을 계산한다.
- `PaperBroker`가 잔여 수량 취소를 원문 이벤트로 기록한다.

## 제외 범위

- 키움 OpenAPI+, Windows COM/Qt 연결을 수행하지 않는다.
- 계좌번호·토큰·비밀번호·인증서를 읽거나 저장하지 않는다.
- 실제 시세 조회, 실계좌 주문, 모의계좌 주문, 취소 API 호출을 수행하지 않는다.
- Vercel·관리형 DB·운영 배포를 수행하지 않는다.

## 변경 파일

- `verification/paper.py`: 조회 전용 gateway, 원문 이벤트 log, 결정적 paper broker를 제공한다.
- `tests/test_paper_verification.py`: 조회 차단, 원문 replay, 부분체결·취소 시나리오를 검증한다.
- `docs/AUTOMATION-DEVELOPMENT-PLAN.md`: STEP 06 상태를 갱신한다.

## RED → GREEN 근거

### RED

신규 `verification.paper` 모듈이 없을 때 테스트 수집 단계에서 `ModuleNotFoundError: No module named 'verification'`로 실패했다.

### GREEN

로컬 paper harness를 추가한 뒤 조회 전용 주문 차단, 원문 이벤트 중복 제거·재생, 부분체결 후 잔여 취소 테스트 9개가 통과했다. 전체 Python 회귀도 143개가 통과했다. 독립 리뷰에서 발견한 얕은 복사, 비정수 수량, 비유한·지수형 가격 입력, 충돌 event ID, 지정가 위반 체결, 비문자 side 입력 문제를 RED 회귀 테스트와 함께 수정했다.

## 자동검사 결과

```text
PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q tests/test_paper_verification.py
9 passed in 0.16s

PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q
143 passed in 2.88s

python3 -m py_compile verification/paper.py tests/test_paper_verification.py
passed

ruff check verification/paper.py tests/test_paper_verification.py
not run: ruff unavailable in the container
```

## 보안·운영 경계

- 이 단계의 broker는 메모리 내 결정적 simulator이며 외부 네트워크를 호출하지 않는다.
- 조회 전용 gateway와 paper broker를 별도 타입으로 분리해 실수로 주문 경계를 우회하지 않게 한다.
- 원문 이벤트는 재처리 근거로만 사용하며, 불명확한 외부 주문 결과를 자동 재전송하지 않는다.
- 실제 키움 모의환경 검증은 Windows native environment에서 별도 승인·검증해야 한다.

## 독립 검토

1차 독립 reviewer는 원문 이벤트의 얕은 복사, 비정수 수량, 비유한·지수형 가격 입력을 지적했다. 2차 독립 reviewer는 충돌 event ID 은닉과 지정가 위반 체결을 지적했다. 3차 독립 reviewer는 비문자 side 입력이 TypeError로 빠지는 경로를 지적했다. 각 결함에 RED 회귀 테스트를 추가하고 deepcopy·명시적 수량·plain-decimal·충돌·지정가·타입 검증으로 수정했다. 최종 reviewer(`sa-0-8a23403d`)는 `passed: true`를 반환했다.

## 완료 조건

- 특정 테스트와 Python 전체 회귀가 통과한다.
- 문법 검사와 가능한 정적 검사가 통과한다.
- 독립 reviewer가 `passed: true`를 반환한다.
- 문서와 구현이 일치한다.
- 단계 커밋과 원격 SHA를 읽어 검증한다.
