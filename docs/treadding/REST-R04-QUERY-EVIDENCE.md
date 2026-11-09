# R04 조회 증거 기록

상태: 2026-11-06 지정 실행기에서 실제 모의계좌 5건 읽기와 장중 WebSocket 수신을 확인했다. 계좌 identity mapping과 주문/체결 연결은 미확정이며 `can_reconcile=false`, `orders_enabled=false`를 유지한다.

## 현재 판정

- 오프라인 코드·합성 응답 검증에 더해, 2026-11-06 실제 모의계좌 5건 조회와 장중 WebSocket 시세 관측을 기록했다.
- 조회는 모두 complete, 각 1 page였다. 보유 조회 1행은 미매핑 상태이며 나머지 미체결·주문·체결 조회 행은 주문 전 0이었다.
- WebSocket은 1 connection에서 24 quotes, malformed 0, `fresh_before_close=true`를 기록했다.
- 실제 계좌 identity mapping 및 사후 주문/체결 연결은 미확정이다. `can_reconcile=false`, `orders_enabled=false`를 유지한다.
- 이전 환경에서 수집한 자료는 [참고용 과거 조회 기록](../reference/legacy-development/REST-R04-QUERY-EVIDENCE.md)에 둔다. 과거 자료를 현재 실증으로 승격하지 않는다.

## 2026-11-04 오프라인 미매핑 보유 행 표시

- 완전한 REST 조회 묶음에 보유 행이 있으면 `BROKER_POSITIONS_UNMAPPED`와 행 개수만 구분해 표시한다. 조회 응답의 원문 행을 가상 원장에 복사하거나 managed 보유량으로 반영하지 않는다.
- 행이 없는 묶음도 계좌 식별 증거가 되지 않으므로 `BROKER_IDENTITY_MAPPING_UNVERIFIED`를 유지한다. 잘못된 행 구조는 `POSITION_ROWS_UNCONFIRMED`로 닫는다.
- 이 오프라인 가드는 broker identity mapping이나 실제 외부 보유 판정을 만들지 않는다. `can_reconcile=false`, `orders_enabled=false`는 변경하지 않았다. 합성 데이터 테스트만 수행했으며 실제 브로커 조회는 하지 않았다.

## 2026-11-06 실제 모의 조회·시세 관측

- 실행 시각: 12:51~12:58 KST. 프로젝트 Python 3.15.2 x64, 지정 실행기.
- 읽기 전 조회 5건은 모두 `complete=true`, `QUERY_COMPLETE_ONLY`, 1 page였다: `kt00018` 1 row, `ka10075` 0, `kt00007` 0, `kt00009` 0, `ka10076` 0.
- `kt00018` 행은 broker 보유 1행으로만 관측했고 managed 원장에 연결하지 않았다. 따라서 `account_reconciled=false`, `can_reconcile=false`다.
- WebSocket: 1 connection, `quotes_observed=24`, `malformed_frames=0`, `fresh_before_close=true`. 주문 후 연결 확인은 R05 실측 섹션에 기록한다.
- 사용자 요청으로 허용된 모의 1주 지정가 주문을 시도했고 `ORDER_ACKED`를 받았다. 사후 linkage는 아직 미확정이라 R04 identity mapping이나 reconciliation을 승격하지 않는다.
- 다음: 사용자가 HTS에서 주문의 미체결/체결을 확인하고 결과를 제공해야 한다. 미확정 상태에서 재주문·자동 취소·원장 연결은 하지 않는다.

## 증거 추가 양식

실제 실행은 별도 승인과 지정 PC에서 수행한 뒤, 민감 정보를 제거하고 사실만 기록한다.

```markdown
## 실측 — <YYYY-MM-DD HH:MM KST>

- 실행기: <프로젝트 격리 환경 경로·버전 확인 결과>
- 명령 범주: <오프라인 예열 | 읽기 전용 조회 | WebSocket 수신>
- 결과: <완료 여부·사유 코드·pages·rows·수신 개수>
- 계좌/주문 연결: <확인 필드의 존재와 일치 개수만, 원문 식별자 제외>
- 미확정 항목: <Q-ID 및 사유>
- 다음 단계: <차단 또는 승인 후 확인할 행동>
```

계좌번호, 키, 토큰, 주문번호, 원문 응답을 남기지 않는다. 미완전 응답이나 인증 실패는 계좌가 비었다는 근거가 아니며, 합성·오프라인 응답은 브로커 증거가 아니다.
