# CherryPulse Web Board

Vue 3 + TypeScript 기반의 트레이딩 상태 보드입니다. 현재 단계는 **mock-only**이며 증권사 API, Python 주문 엔진, 실계좌와 연결되지 않습니다.

## 포함 기능

- 등록·설정
- 매수 감시
- 매수 주문 중
- 보유·매도 감시
- 매도 주문 중
- 종료
- 엔진 오프라인 및 실주문 비활성 표시
- 부분체결·청산 진행 상태 예시
- 반응형 사이드바와 가로 스크롤 보드

## 요구 환경

`package.json`의 `engines.node` 조건을 충족하는 Node.js를 사용합니다.

## 실행

```sh
npm install
npm run dev
```

## 검사

```sh
npm run format:check
npm run lint
npm run type-check
npm run test:unit -- --run
npm run build
```

## 안전 경계

- `src/data/mockTrading.ts`의 예시 데이터만 사용합니다.
- 화면의 가격과 주문 상태는 실제 데이터가 아닙니다.
- 등록 카드나 메뉴를 조작해도 주문이 전송되지 않습니다.
- 실제 연동은 공통 계약, 인증, 설정 수락과 Windows 모의환경 검증 이후 별도 단계에서 진행합니다.
