# STEP 04 — 매수·일반 매도 패턴 평가 모듈

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-22 |
| 작업 브랜치 | `feat/automated-rebuild-20260921` |
| 실행 범위 | 순수 Python 패턴 조건 평가기와 테스트 |
| 안전 경계 | 실계좌·실브로커·실주문·운영 배포 부작용 없음 |

이 단계는 이전 단계 커밋 `a799e49` (STEP 03 손절 우선) 위에서 수행한다. 어댑터·가상 dispatcher와는 아직 연결하지 않는다.

## 구현 범위

- `patterns/evaluation.py`에 두 조건 평가기를 추가한다.
  - `evaluate_price_threshold`: 가격 돌파(GTE/LTE) 평가
  - `evaluate_average_price_stop`: 평균 체결가 대비 비율 손절 평가
- 입력은 공통 계약과 같은 정규 십진 문자열을 요구한다. 비규 입력은 `PATTERN_INVALID_DECIMAL`로 거절한다.
- Binary floating-point 비교를 사용하지 않고 Decimal로 정확 비교한다.
- 특정 투자 값(몇 %, 어떤 가격)은 하드코딩하지 않는다. 입력만을 평가한다.

## 제외 범위

- 실제 증권사 API·브로커 어댑터와 연결하지 않는다.
- 패턴 활성화(실제 감시 시작 요청)는 사용자 승인 후 별도 단계에서 진행한다.
- 패턴 수치·시간 단위·재발동·재진입·미체결 정책 `Q12`는 아직 사용자 승인한 특정 패턴이 없으므로 현재 평가기는 실제 활성화가 아니다.

## 변경 파일

- `patterns/__init__.py`: 패턴 평가 패키지를 추가한다.
- `patterns/evaluation.py`: Decimal 기반 가격·평균가 손절 조건 평가기를 제공한다.
- `tests/test_pattern_evaluators.py`: 평가기 동작과 입력 거부를 검증한다.
- `docs/PATTERN-SPEC-REBUILD-00.md`: 평가 규격과 활성화 선행 조건을 기록한다.
- `docs/CherryPulse-KR-01-Rebuild-Plan.md`: REBUILD-06 상태를 갱신한다.

## TDD 기록

### RED

초기 테스트는 패키지가 존재하지 않아 `ModuleNotFoundError: No module named 'patterns'`로 실패했다. 추가한 입력 형식 테스트도 구현 전 `PATTERN_INVALID_DECIMAL` 예외가 발생하지 않아 실패했다.

### GREEN

`patterns/__init__.py`와 `patterns/evaluation.py`를 추가하고, 가격 돌파·평균가 대비 조건 평가를 Decimal 기반으로 구현했다. 공통 계약과 동일한 plain-decimal 입력 검증과 고정밀 Decimal 컨텍스트를 추가한 뒤 특정 테스트 6개와 전체 회귀 134개가 통과했다.

## 자동검사 결과

- Python 특정 테스트 `tests/test_pattern_evaluators.py`: 6개 통과
- Python 전체 회귀: 134개 통과

```text
PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q tests/test_pattern_evaluators.py
6 passed in 0.37s

PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q
134 passed in 5.40s

python3 -m py_compile patterns/evaluation.py tests/test_pattern_evaluators.py
git diff --cached --check
clean
```

## 보안·운영 경계

- 평가기는 bool 결과만 반환하며 주문·어댑터·계좌 자격증명에 접근하지 않는다.
- 실계좌 주문, 모의계좌 주문, 브로커 API 호출, 운영 배포는 범위 밖이다.
- 패턴 수치와 재발동 정책 승인 전에는 엔진 감시 흐름에 연결하지 않는다.

## 다음 단계의 선행 조건

- 사용자가 수치·시간 단위·재발동·재진입·미체결 정책을 명시 승인
- 승인된 패턴이 `contracts.models`의 `PatternVersion`을 구체화하도록 공통 fixture에 반영
- 패턴 조건이 엔진에 연결될 때마다 TDD 기록과 독립 검토를 앞당겨 사용해야 한다.

## 독립 검토

1차 리뷰(`sa-0-73f4f378`)에서 고정밀 Decimal 반올림 결함이 발견되어 회귀 테스트와 `localcontext` 수정으로 해결했다. 2차 리뷰(`sa-0-7642beff`)는 `passed: true`를 반환했고 보안·논리 결함이 없음을 확인했다.

## 완료 조건

- 특정 테스트와 전체 회귀 테스트가 통과한다.
- `git diff --cached --check`가 통과한다.
- 독립 reviewer가 `passed: true`를 반환한다.
- 단계 문서와 구현이 일치한다.
- 단계 커밋과 원격 SHA를 읽어 검증한다.
