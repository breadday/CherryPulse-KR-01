# 개발 가능한 작업과 외부 차단 항목

기준 시점: 2026-10-22, main `1188b9f`.
목적: 소프트웨어 개발 진행과 실제 계좌·서버·기기 인수를 분리해, 같은 미완료 목록만 반복하지 않도록 한다.

## 지금 자동으로 개발·검증할 수 있는 범위

- 결정된 계약에 대한 오프라인 구현, 단위/회귀 테스트, lint/type 검사, CI.
- 예약 runner의 안전한 실패 진단. 원시 브로커 응답·stderr·토큰·계좌번호·주문번호는 저장하지 않고 단계 코드와 제한된 실패 범주만 기록한다.
- API 계약이 제공된 뒤의 보드 클라이언트·mock 테스트. 계약이 없는 현재는 endpoint나 인증 방식을 추측하지 않는다.
- 검증 결과와 차단 사유 문서화. 코드 테스트 통과만으로 실제 계좌/기기 인수를 완료 처리하지 않는다.

## 이번 작업에서 구현한 소프트웨어 단위

**R045 WebSocket 실패 관측성 — 구현·부분 검증 완료**

- 2026-10-22 실행은 `PREWARM=0`, `READ_BEFORE=0`, `QUOTE_WS=1`, `ABORTED`; 주문 단계는 호출되지 않았다.
- `StreamCapture`에 제한된 `failure_stage`(TOKEN/PACING/CONNECT/PROTOCOL/CLOSE)와 `failure_kind`(고정 코드) 추가. setup 단계 실패도 `SETUP`과 안전한 범주만 출력한다.
- Runner는 허용 목록에 있는 두 필드만 manifest에 보존한다. 예외 메시지, raw frame, stderr, 인증정보는 제외한다.
- 테스트 우선으로 실패 재현 후 구현했으며 관련 테스트 23개 통과, Ruff check/format 통과. 전체 verifier는 exit 0 / 6 checks, GitHub PR #14의 `offline-rest`와 `windows-engine` CI도 통과했다.
- 이 기능은 관측성을 높일 뿐 실제 WebSocket 성공이나 R04/R05 완료를 뜻하지 않는다.

## 외부 검증이 필요한 미완료 항목

| 우선순위 | 작업 | 완료 판정 | 필요한 주체/자료 |
|---|---|---|---|
| P0 | R04: 지정 PC 모의계좌 읽기·실제 장중 WS 수신 | 정해진 조회 5건의 완료 근거와 WS `quotes_observed > 0`, `fresh_before_close=true`를 마스킹된 증거에 기록 | 지정 Windows PC, 모의계좌, 장중 접근. 비밀 키는 로컬 환경변수에만 보관 |
| P0 | R05: 허용된 모의 1주 지정가 및 사후 이력/연결 확인 | 접수/거절/UNKNOWN 구분, HTS 미체결 확인(필요 시 사람 취소), 사후 조회·연결 결과 및 체크리스트 기록 | 사용자의 명시적 승인과 HTS 접근. UNKNOWN이면 재시도하지 않음 |
| P1 | R08/TASK-3: 보드 REST API 계약·서버 연결 | `/boards`, `/items`, `/patterns`의 CRUD와 실패/버전 충돌 mock 테스트, UI 인수 | 서버 담당자가 아래 API 자료 제공 |
| P2 | TASK-4: iOS/Android 실기기 6/6 | iOS Safari 및 Android Chrome에서 정의된 6개 항목 모두 기록 | 실제 iPhone/iPad와 Android 기기 접근; PC 에뮬레이션은 대체 근거가 아님 |
| P2 | 클라우드 인증·동기화 | 선택된 provider/보안 경계에 따른 연결·권한·동기화 검증 | 사용자가 provider, 계정 소유권, 데이터 위치/보존 기준을 결정 |
| 후속 | R05 dispatcher, R06 보호 연결, R07 무인 운영 | UNKNOWN/부분체결/취소경합/재시작/계좌대조 및 장애 복구 승인 테스트 | R04/R05 실제 근거와 단계별 운용 승인. 선행 게이트 전에 실제 주문 경로를 열지 않음 |

## 다른 GPT/서버 담당자에게 요청할 자료

보드 REST 계약을 요청할 때 다음 항목을 **비밀정보 없이** 받아 저장소에 제공한다.

1. OpenAPI/Swagger 또는 버전이 명시된 API 명세와 실제 서버 저장소/서비스 담당자.
2. 개발·운영 base URL 구분, 인증 방식(토큰 값은 보내지 말고 방식/수명/갱신만), CORS 및 권한 범위.
3. `boards`, `items`, `patterns` 각 endpoint의 method/path, 필수·선택 필드, 성공/오류 응답 예시.
4. 생성 중복 방지/idempotency, 동시 수정·버전 충돌, 삭제·보관 semantics, pagination/rate limit.
5. 승인된 테스트 환경과 mock/fixture 또는 재현 가능한 acceptance tests.

증권사 검증은 GPT 답변이나 문서 추정으로 대체하지 않는다. 설치된 모의 환경에서 실행된 마스킹 결과만 실증 근거로 쓴다. 계좌번호, app key/secret, access token, 원문 주문번호를 채팅이나 문서에 보내지 않는다.

## 예약 작업 안전 고지 — 기준 시점 스냅샷

`CherryPulse-R045-Demo` Windows 예약 작업은 평일 09:30에 활성화되어 있다. 2026-10-22 조회 당시 다음 실행은 2026-10-23 09:30 KST였다. Runner는 사전 조회와 WS 확인이 성공하면 모의 1주 지정가를 한 번 시도하도록 되어 있다. 이 예약은 **개발 자동화가 아니라 실증 runner**이며, 이 문서 작성은 예약을 수정·중지하지 않았다. 실행 후 manifest와 HTS 미체결을 감독 확인하고, 증거가 없으면 R04/R05 상태를 올리지 않는다.

## 2026-10-22 API 자료 요청 후속

[인계 패키지](../api/BOARD-API-HANDOFF.md)에 OpenAPI 제안·합성 fixture·
환경/소유/보존 확인표·실증 공유 항목·모바일 수락 기준을 추가했다.
서버에서 받은 확정 명세가 아니므로 TASK-3 실제 호스트/인증/서버 구현 차단은 유지한다.
클라우드 선택과 물리 기기 결과는 미확정이다. 담당자 회신 후 확정 계약만 구현에 적용한다.
