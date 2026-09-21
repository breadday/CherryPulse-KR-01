# AUTOMATION STEP 01 — Vue Mock 트레이딩 보드

- 수행일: 2026-09-21
- 브랜치: `feat/automated-rebuild-20260921`
- 이전 단계 커밋: `359b17ca396fff26f97d6c499a1fe81c7a7239d9`

## 구현 범위

- `web/`에 Vue 3 + TypeScript + Vite 프로젝트를 생성했다.
- Vue Router, Pinia, Vitest, ESLint, Oxlint, Prettier를 구성했다.
- 다음 6개 실행 상태를 보드 열로 표시한다.
  1. 등록·설정
  2. 매수 감시
  3. 매수 주문 중
  4. 보유·매도 감시
  5. 매도 주문 중
  6. 종료
- 종목, 매수·매도 패턴, 현재가, 수량, 상태 설명과 업데이트 시각을 표시한다.
- 부분체결 보호 대기와 청산 진행 중 상태를 예시로 표시한다.
- 엔진 오프라인, 실주문 비활성, Mock 데이터 모드를 화면 상단에 고정 표시한다.
- 좁은 화면에서는 내비게이션과 요약 영역을 축소하고 보드는 가로 스크롤로 유지한다.

## 제외 범위

- Python 실행 엔진 호출
- 키움 OpenAPI+ 및 계좌 연결
- 실제 시세, 주문, 체결 데이터
- 로그인과 관리형 DB
- 보드 카드 이동을 통한 주문 상태 변경
- Vercel 배포

## TDD 기록

### RED

먼저 다음 기대 동작을 테스트로 작성했다.

- Mock 데이터 배너가 보여야 한다.
- 6개 실행 상태 열이 모두 보여야 한다.
- 6개 예시 종목 카드가 상태별로 하나씩 배치돼야 한다.
- 엔진 오프라인과 실주문 비활성 상태가 보여야 한다.
- Pinia store가 각 상태별 항목과 전체 개수를 정확히 계산해야 한다.
- 한 Pinia 인스턴스의 mock 수정이 새 인스턴스에 누출되지 않아야 한다.

최초 실행 결과:

- `tradingBoard` store가 존재하지 않아 import 실패
- 기본 Vue 화면에는 Mock 배너와 보드 열이 없어 App 테스트 실패

### GREEN

도메인 타입, mock fixture, Pinia store, 보드/카드 컴포넌트와 화면 스타일을 최소 구현한 뒤 테스트가 통과했다.

## 검증 결과

```text
format:check  통과
Oxlint/ESLint 통과
vue-tsc       통과
Vitest        2개 파일, 3개 테스트 통과
Vite build    통과
npm audit     취약점 0건
```

빌드 산출물:

```text
dist/index.html
CSS 약 6.06 kB
JS 약 98.35 kB
```

`dist/`, `node_modules/`, `.eslintcache`는 Git에 포함하지 않는다.

## 운영 한계

모든 카드와 가격은 `src/data/mockTrading.ts`에 정의한 예시다. 이 단계의 화면은 제품 흐름과 상태 표현을 검토하기 위한 것으로 주문 실행 가능 상태를 의미하지 않는다.

## 다음 단계

Python Pydantic 모델과 TypeScript 타입이 함께 사용할 공통 fixture를 만들고 종목, 패턴 버전, 실행 설정, 주문·체결 및 운영 상태 계약을 고정한다.
