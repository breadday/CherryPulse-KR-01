# STEP 05 — 동기화 상태와 보드 표시

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-22 |
| 작업 브랜치 | `feat/automated-rebuild-20260921` |
| 실행 범위 | 웹 조회 상태·로컬 outbox 분리, 이벤트 순서 처리, 오프라인·지연 표시 |
| 안전 경계 | 실계좌·실브로커·실주문·운영 배포 부작용 없음 |

## 구현 범위

- `sync/state.ts`에 직렬화 가능한 동기화 상태를 정의한다.
- 동일 이벤트 ID를 중복 적용하지 않는다.
- 스트림별 역순 이벤트를 현재 조회 상태에 적용하지 않는다.
- 스트림별 웹 조회 모델과 로컬 outbox 명령을 별도 컬렉션으로 유지한다.
- 연결 상태와 마지막 이벤트 시각으로 최신·지연·오래됨 상태를 계산한다.
- 보드 상단에 동기화 연결·신선도 상태를 표시한다.

## 제외 범위

- 실제 WebSocket, HTTP polling, 서버 outbox 전송기는 연결하지 않는다.
- 서버 저장소, 인증, 오프라인 재전송 API는 구현하지 않는다.
- Vercel·관리형 DB 배포를 수행하지 않는다.
- 실계좌 주문, 모의계좌 주문, 브로커 API 호출을 수행하지 않는다.

## 변경 파일

- `web/src/sync/state.ts`: 순수 동기화 상태 reducer와 요약 함수를 추가한다.
- `web/src/stores/tradingBoard.ts`: 보드 store에 동기화 상태 요약을 연결한다.
- `web/src/App.vue`: 동기화 연결·신선도를 보드 상단에 표시한다.
- `web/src/__tests__/sync.spec.ts`: 중복·역순 이벤트, outbox 분리, 오프라인·최신 상태를 검증한다.
- `web/src/__tests__/App.spec.ts`: 동기화 상태 표시를 검증한다.
- `docs/AUTOMATION-DEVELOPMENT-PLAN.md`: STEP 05 상태를 갱신한다.

## RED → GREEN 근거

### RED

- 신규 sync 모듈이 없을 때 `sync.spec.ts`가 `../sync/state` import 해석 실패로 RED가 되었다.
- 보드에 동기화 표시가 없을 때 `App.spec.ts`가 `[data-testid="sync-status"]`를 찾지 못해 RED가 되었다.

### GREEN

- 순수 reducer를 추가한 뒤 sync 특정 테스트 5개가 통과했다.
- store·App에 오프라인/오래됨 표시를 연결한 뒤 관련 테스트가 통과했다.
- 독립 리뷰에서 발견한 다중 스트림 덮어쓰기, 미래 시각, 잘못된 sequence, 시간 경과 미갱신 문제를 회귀 테스트와 함께 수정했다.
- 최종 전체 웹 테스트는 29개 통과했다.

## 자동검사 결과

```text
HOME=/tmp ../.tools/node-v24.21.0/bin/node node_modules/vitest/vitest.mjs run
Test Files  4 passed (4)
Tests       29 passed (29)

HOME=/tmp ../.tools/node-v24.21.0/bin/node node_modules/vue-tsc/bin/vue-tsc.js --build
passed

HOME=/tmp ../.tools/node-v24.21.0/bin/node node_modules/vite/bin/vite.js build
built successfully; 34 modules transformed

HOME=/tmp ../.tools/node-v24.21.0/bin/node node_modules/oxlint/bin/oxlint .
passed
```

## 보안·운영 경계

- 동기화 모듈은 메모리 내 조회 모델과 로컬 outbox만 다룬다.
- 이벤트 적용은 중복·역순을 무시하며, 불확실한 외부 주문 결과를 자동 재전송하지 않는다.
- 현재 화면은 오프라인·오래됨 상태를 명시하고 실주문 가능 상태로 표시하지 않는다.
- 실제 네트워크 연결과 배포는 별도 설계·승인 단계에서 수행한다.

## 독립 검토

1차 독립 reviewer는 다중 스트림 상태 덮어쓰기, 미래 시각 처리, 잘못된 sequence 수용, 시간 경과 후 freshness 미갱신을 지적했다. 2차 독립 reviewer는 교차 스트림 최신 시각 보존과 비표준 timestamp 거부를 추가로 지적했다. 3차 독립 reviewer는 달력상 존재하지 않는 timestamp 수용을 지적했다. 4차 독립 reviewer는 aggregate read model의 교차 스트림 필드 충돌을 지적했다. 5차 독립 reviewer는 빈 식별자와 잘못된 freshness threshold 수용을 지적했다. 각 결함에 RED 회귀 테스트를 추가하고 reducer 입력 경계를 강화했다. 최종 reviewer(`sa-0-bb830fe2`)는 `passed: true`를 반환했다.

## 완료 조건

- 웹 특정·전체 테스트가 통과한다.
- TypeScript 검사·빌드·lint가 통과한다.
- 독립 reviewer가 `passed: true`를 반환한다.
- 문서와 구현이 일치한다.
- 단계 커밋과 원격 SHA를 읽어 검증한다.
