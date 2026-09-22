# AUTOMATION STEP 02 — 공통 계약과 API 경계

- 수행일: 2026-09-22
- 브랜치: `feat/automated-rebuild-20260921`
- 이전 단계 커밋: `2e7854b1a6e4310794f4f0dde5be42ccad67d3b0`

## 구현 범위

- Python Pydantic 모델과 TypeScript 런타임 검증기가 같은 JSON fixture를 읽는다.
- 알 수 없는 필드와 잘못된 원시값·enum·식별자·십진 문자열·시각을 거절한다.
- UUID는 하이픈이 있는 형식만 허용하고 비교 전에 소문자 정규화한다.
- TypeScript 정수는 JavaScript 안전 정수 범위 안에서만 허용한다.
- 다음 공통 계약을 정의했다.
  - 종목과 시장
  - 버전이 있는 매수·매도 패턴
  - 실행 설정 요청·수락·거절·만료 상태
  - 주문 상태와 수량 보존
  - 체결과 주문 연결
  - 엔진·실주문·데이터·대조 운영 상태
- 설정, 패턴, 주문, 체결 사이의 식별 관계를 검증한다.
- Python과 TypeScript가 수락 설정의 요청 버전과 적용 버전 불일치를 같은 오류 코드로 거절한다.

## 변경 파일

```text
README.md
contracts/__init__.py
contracts/models.py
contracts/fixtures/step02-contract.json
tests/test_contracts.py
web/src/contracts/models.ts
web/src/__tests__/contracts.spec.ts
docs/AUTOMATION-DEVELOPMENT-PLAN.md
docs/AUTOMATION-STEP-02-CONTRACTS.md
pyproject.toml
```

## 제외 범위

- HTTP API 서버와 엔드포인트
- 관리형 DB와 웹 저장
- 실제 증권사 계좌·시세·주문 연결
- 키움 OpenAPI+ 또는 REST API 호출
- 패턴 조건 평가와 주문 제출
- 기존 SQLite 실행 원장의 모델 교체
- 별도 아이디어인 주매매건·다중 증권사·가격밴드 분할매매

## 주요 계약

### 실행 설정

상태는 `PENDING`, `ACCEPTED`, `REJECTED`, `EXPIRED`다.

- `PENDING`: 적용 버전과 거절 사유가 없어야 한다.
- `ACCEPTED`: 적용 버전이 요청 버전과 같고 거절 사유가 없어야 한다.
- `REJECTED`: 적용 버전이 없고 거절 사유가 있어야 한다.
- `EXPIRED`: 적용 버전과 거절 사유가 없어야 한다.
- 만료 시각은 요청 시각보다 뒤여야 한다.

### 주문과 체결

- 지정가는 양수 가격이 필요하다.
- 시장가는 가격이 없어야 한다.
- 거절 주문을 제외하면 `주문수량 = 체결수량 + 취소수량 + 활성잔량`을 만족해야 한다.
- 부분체결은 체결수량과 활성잔량이 모두 양수여야 한다.
- fixture의 체결 합계는 주문의 누적 체결수량과 같아야 한다.
- 체결 ID 중복과 다른 주문에 연결된 체결을 거절한다.
- 존재하지 않는 달력 날짜와 잘못된 UTC 오프셋을 거절한다.

### 패턴과 운영 상태

- 패턴 ID와 버전 조합은 중복될 수 없다.
- 실행 설정의 매수 패턴은 `BUY`, 매도 패턴은 `SELL`이어야 한다.
- 실주문 활성 상태는 엔진 `ONLINE`과 데이터 모드 `LIVE`를 동시에 요구한다.

## TDD 기록

### RED

먼저 양쪽 런타임이 같은 fixture를 수락하고 잘못된 수락 버전을 거절하는 테스트를 작성했다.

- Python: `contracts.models`가 존재하지 않아 수집 실패
- TypeScript: `../contracts/models`를 찾을 수 없어 Vitest 실패

두 실패가 구현 부재 때문임을 확인한 뒤 모델을 작성했다.

### GREEN

- Python Pydantic `ContractBundle`이 공통 fixture를 수락했다.
- TypeScript `parseContractBundle()`이 같은 fixture를 수락했다.
- 양쪽 모두 `ACCEPTED_VERSION_MISMATCH`를 거절했다.
- TypeScript 검증기는 반환한 계약 객체와 하위 객체를 읽기 전용으로 정의했다.

독립 fail-closed 검토에서 발견된 안전 정수 범위, 존재하지 않는 달력 날짜, UUID 대소문자·형식 불일치를 각각 재현하는 실패 테스트를 먼저 추가했다. 세 테스트의 RED를 확인한 뒤 공통 검증 규칙을 수정해 GREEN으로 전환했다.

후속 재검토에서 Python의 `AwareDatetime`이 숫자 Unix 시각과 비표준 문자열을 허용한다는 계약 불일치를 발견했다. Python에도 웹과 같은 `YYYY-MM-DDTHH:MM:SS[.sss](Z|±HH:MM)` 입력 문법을 적용하고 양쪽 회귀 검사를 추가했다.

추가 재검토에서 JavaScript 안전 정수 상한, 밀리초를 넘는 시각 정밀도, Python의 불리언·스키마 버전 강제 변환 차이를 발견했다. 정수는 양쪽 모두 `Number.isSafeInteger`와 같은 범위·의미를 사용하고, 시각 소수부는 최대 3자리로 제한하며, 불리언과 필수 스키마 버전을 명시적으로 검증하도록 수정했다.

마지막 재검토에서 TypeScript가 누락된 `schema_version`을 1로 기본 처리하는 비대칭을 발견했다. 기본값을 제거하고 Python과 TypeScript 모두 해당 필드를 필수로 요구하도록 수정했다.

밀리초 문법 재검토에서 현재 Linux Python의 `datetime.fromisoformat()`이 소수부 1·2자리를 거절하는 차이를 발견했다. 검사용 소수부를 3자리로 정규화한 뒤 달력 유효성을 검사하도록 수정하고, 양쪽에 1·2·3자리 허용 회귀 검사를 추가했다.

## 검증 결과

```text
Python Ruff          통과
Python 계약 테스트   17개 통과
Web format:check     통과
Oxlint/ESLint        통과
vue-tsc              통과
Vitest               3개 파일, 20개 테스트 통과
Vite build           통과
npm audit            취약점 0건
```

핵심 검증 명령:

```bash
PYTHONPATH=.tools/python-packages python3 -m ruff check contracts tests/test_contracts.py
PYTHONPATH=.tools/python-packages python3 -m ruff format --check contracts tests/test_contracts.py
PYTHONPATH=.tools/python-packages python3 -m pytest tests/test_contracts.py -q --noconftest

cd web
node ./node_modules/vitest/vitest.mjs run
node ./node_modules/vue-tsc/bin/vue-tsc.js --build --force
node ./node_modules/prettier/bin/prettier.cjs --check --experimental-cli .
node ./node_modules/oxlint/bin/oxlint .
node ./node_modules/eslint/bin/eslint.js . --no-cache
node ./node_modules/vite/bin/vite.js build
npm audit --audit-level=low
```

빌드 산출물:

```text
dist/index.html
CSS 약 6.06 kB
JS 약 98.35 kB
```

## 검증 환경 제한

현재 Linux 검토 환경에서는 기존 `execution/ownership.py`가 Windows 전용 `msvcrt`를 import하므로 기존 Python 전체 테스트를 실행할 수 없다. 이번 변경은 기존 `execution/`을 수정하지 않았고 새 계약 테스트는 `--noconftest`로 분리해 통과했다. Windows 환경에서 기존 98개 실행 검사를 다시 수행하는 절차는 유지한다.

웹 검사는 프로젝트 요구 범위를 충족하는 Node.js 24 환경에서 실행했다.

## 보안·운영 한계

- fixture의 종목·계좌·주문·체결은 모두 예시 데이터다.
- 비밀번호, 토큰, 실제 계좌번호와 실제 주문 API를 사용하지 않는다.
- 이 단계는 데이터 경계를 고정하며 주문 실행 권한을 만들지 않는다.
- Python과 TypeScript 검증기는 별도 구현이므로 계약 변경 시 양쪽 테스트와 fixture를 함께 수정해야 한다.

## 다음 단계

부분 매수 체결을 보호 의무로 등록하고, 손절 조건이 발동했을 때 기존 예약·미확정 주문·수량 불일치를 검사한 뒤 청산 의무를 생성하는 STEP 03을 진행한다. 실제 증권사 주문 호출은 추가하지 않는다.
