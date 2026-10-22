# 보드 API·클라우드·실증 인계 패키지

작성: 2026-10-22. 조사 기준 main `dcb0035`.

## 확인된 현재 상태

- 화면: `web/board/`. 브라우저 localStorage 초안과 백업·미리보기만 구현돼 있다.
- `/boards`, `/items`, `/patterns` 서버 라우트·OpenAPI·서버 인증 설정·개발/운영 URL은 현재 저장소에서 확인되지 않았다.
- `contracts/settings.py`와 `sync/polling.py`는 내부 실행 계약/가상 동기화다. 웹 CRUD 서버로 노출할 수 없다.
- R04/R05와 모바일 인수는 아래 실증 자료가 들어올 때까지 대기다.

## 1. 서버 담당자가 검토할 API 계약안

[OpenAPI 3.0.3 JSON](board-api.openapi.draft.json)은 **새 계약 제안**이다.
실제 서버에서 받은 Swagger가 아니다. `0.1.0-draft`,
`PROPOSED_NOT_DEPLOYED`로 표기하며 서버 URL은 호출 불가 `.invalid`다.
실서버 계약이 오면 별도 검토 후 차이를 기록하고 그 명세를 기준으로 구현한다.
현재 보드의 fetch 대상이나 저장 방식을 변경하지 않았다.

| 경로 | 작업 | 결과 |
|---|---|---|
| `/boards` | GET / POST | 소유 보드 목록 / 초안 보드 생성 |
| `/boards/{id}` | GET / PATCH | 조회 / 이름·보관·복원 |
| `/items?boardId=...` | GET | 해당 보드의 종목 목록 |
| `/items` | POST | 종목 생성 |
| `/items/{id}` | GET / PATCH | 조회 / 이름·출처·메모·패턴 연결·보관·복원 |
| `/patterns?boardId=...` | GET | 해당 보드의 패턴 버전 목록 |
| `/patterns` | POST | 새 패턴 계열 또는 최신 버전을 기반으로 새 불변 버전 생성 |
| `/patterns/{id}` | GET / PATCH | 버전 조회 / 활성·비활성 상태 변경 |

하드 DELETE는 초기 범위에 없다(HTTP 405). 종목/보드 보관은 PATCH,
패턴 삭제 대신 비활성화다. 보관·비활성화가 실제 보유 보호를 중단시키지 않는다.
이 API에는 엔진 적용·감시 시작·주문/취소가 없다.

### 인증·권한 (제안, 실제 적용은 미확정)

사용자 OIDC access JWT를 `Authorization: Bearer`로 전달하고 서버에서 서명,
issuer/audience, 만료, 현재 권한을 검증한다. 다른 사용자의 개체는 404,
확인된 소유 개체의 동작 권한 부족은 403. owner 식별자는 토큰에서 결정하고
본문 입력으로 받지 않는다. 키움 토큰·키와 공유하지 않는다.

실서버 담당자가 issuer, audience, JWKS, 역할/권한, 만료 시간, 갱신·로그아웃,
허용 Origin을 작성해야 한다. JWT라는 이유만으로 서명/철회 확인이 완료되지는 않는다.
제안: 운영은 HTTPS, CORS는 명시적 Origin만 허용하고
Authorization/Content-Type/Idempotency-Key/If-Match 헤더를 허용,
ETag/Location/Retry-After를 노출한다. 브라우저 쿠키 인증을 선택하면 CSRF와
SameSite 규칙을 별도 계약으로 바꾼다. 토큰 저장 위치도 이 결정 후 정한다.

### 요청·응답과 초안 매핑

성공: 단건 `{data: resource}`, 목록 `{data: [...], nextCursor: null|string}`.
필드·제약·필수 여부는 OpenAPI를 따른다. 초안의 `patternId`와 `buyPatternId`는
각각 손절/매수 **불변 버전 id**를 참조한다. null은 연결 해제다.
브라우저의 빈 문자열 연결은 API 변환 시 null로 정규화하고 역변환한다.
서버 Pattern.patternId는 **패턴 계열**이므로 Item.patternId와 혼동하지 않는다.
기존 localStorage id가 서버 UUID 형식과 다르면 최초 가져오기 때 새 UUID를 만들고
모든 연결을 하나의 검증된 매핑으로 바꿔야 한다. 초기에는 자동 업로드하지 않는다.

Pattern의 `version`은 규칙 버전, 모든 리소스의 `revision`은 동시 수정 버전이다.
규칙 변경은 POST + `basePatternId`(기존 최신 버전의 id)로 새 id·version을 만들고,
기존 종목 연결은 유지한다. 비활성 버전에 대한 기존 연결은 보존하되 새 연결은 422.
다른 보드·다른 종류·존재하지 않는 패턴 연결도 422. 출처는 빈 값 또는 http/https만,
매수는 지정가·1주 고정·목표가 10만원 상한 등 현행 Q12를 유지한다.
평균가가 없는 비율 손절 미리보기는 평가 보류이며 엔진의 보호 상태가 아니다.

### 동시 수정·재시도·중복

- GET 단건/쓰기 응답의 강한 ETag는 `"revision"` 형식이다. PATCH는 If-Match 필수:
  누락 428, 다르면 412. UI는 재조회 후 충돌을 보여주며 자동 덮어쓰지 않는다.
- 모든 POST/PATCH는 Idempotency-Key 필수. 인증 후 사용자 + method + canonical path +
  key 범위로 원자적으로 기록한다. 내용은 본문과 If-Match를 정규화하여 비교한다.
- 동일 키·동일 내용은 **버전 검사보다 먼저** 저장된 상태코드·본문·ETag를 재생한다.
  인증/권한 검사는 재생 때도 먼저 수행한다. 다른 내용은 409 IDEMPOTENCY_MISMATCH.
- 멱등 결과 보존 24시간은 제안이며 실서버 담당자가 보장 기간을 확정해야 한다.
  기간 경과 후 자동 재생성하지 않고 서버 상태를 재조회한다.
- 같은 보드·종목코드는 보관 포함 UNIQUE. 다른 키로 재생성해도 409 DUPLICATE_ITEM.
  보관 종목을 추가하려면 기존 id 조회 후 PATCH 복원한다.
- 새 패턴 버전은 최신 base와 가족 버전 증가를 한 트랜잭션으로 비교한다.
  동일 base로 경쟁 시 1건만 생성, 나머지 409 STALE_PATTERN_BASE.
- 한 변경의 데이터 갱신·revision·멱등 결과는 같은 트랜잭션으로 확정한다.
  인증 없는 요청·형식 오류는 쓰기를 수행하지 않는다.
- 429/503은 Retry-After, 페이지는 opaque cursor + limit 기본50/최대100.
  정렬은 createdAt,id 고정, 동일 필터·소유 범위에만 커서를 사용한다.
  페이지 전체가 완료되기 전 엔진 대조 완료로 취급하지 않는다.

### 오류 형식

`{error: {code, message, requestId, details?: [{field, reason}]}}`.
400 형식, 401 인증, 403 권한, 404 미발견, 409 중복/멱등/기준버전 경쟁,
412 동시수정, 422 필드/연결, 428 전제조건, 429 제한, 503 일시불가.
message/details에는 토큰·계좌·원문 주문번호·내부 예외를 포함하지 않는다.
예시는 [합성 fixture](board-api.fixtures.json)를 따른다.

### 개발·테스트 환경

현재 실제 API 개발 URL과 테스트 계정은 **미제공**이다. 기존
`http://localhost:8080/`은 정적 보드 주소이며 API 서버가 아니다.
지금 제공하는 것은 OpenAPI와 합성 request/response fixture 및 서버 인수 시나리오다.
실행 중인 mock HTTP 서버·Swagger UI·CRUD 서버를 설치했다는 의미는 아니다.
OpenAPI JSON을 Swagger 편집기에 가져와 검토할 수 있으며 `.invalid`로 실행하지 않는다.

서버 구현 후 개발 환경에서 fixture 기반 정상/오류 테스트를 수행한다.
필수 시나리오: 생성→조회→수정→보관→복원, 미인증401, 다른소유자404,
권한부족403, 동일키재생, 다른내용409, 동일종목409, stale ETag412,
If-Match누락428, 잘못된연결422, 구버전새패턴409, 비활성기존연결보존,
429/503 및 Retry-After, 페이지완료, 네트워크응답유실후동일키재생.
최종 URL·인증·테스트계정과 담당자 제공 없이는 실제 연동 통과로 표시하지 않는다.

## 2. 클라우드 결정표

[환경 확인표](board-api.environment.template.json)에 null/UNDECIDED를 채운다.
기존 목표는 Vercel 웹/API + 관리형 DB + 지정 Windows 엔진이다.
이는 이번에 선택/연결/배포한 서비스라는 뜻이 아니다. 새 서비스/계정을 임의 생성하지 않았다.

| 결정 | 현재 | 확정할 내용 |
|---|---|---|
| 웹/API·DB·사용자 인증 서비스 | 미확정 | 실제 프로젝트·환경·담당 저장소 |
| 계정·결제·관리자 | 미확정 | 사용자 소유 계정, 담당자의 접근·회수 권한 |
| 데이터 소유 | 제안: 사용자 소유 | 운영자·사용자별 소유·내보내기·삭제 권한 |
| 저장 위치 | 미확정 | 데이터/백업 지역, 접근 가능 주체 |
| 원본·로그·백업 보존 | 미확정 | 각각 기간, 삭제/복원/백업 만료 절차 |
| 멱등성 기록 | 제안24시간 | 실서버 보장 기간 |
| 운영 원장 | 현행 지정 PC | 클라우드 초안/표시 복제와 구별; 원장 이전은 별도 과제 |

클라우드에는 기본적으로 보드 초안·설정 수락 상태·필요한 표시용 복제만 둔다.
키움 키·토큰·운영 SQLite·원문 계좌/주문번호를 이 인계 자료에 넣지 않는다.
보존값은 담당자가 답하기 전 임의 숫자로 확정하지 않는다.

## 3. R04/R05 실제 증거 인계

실행 절차·판정은 [기존 실증 체크리스트](../treadding/REST-R04-LIVE-PROBE-CHECKLIST-2026-10-21.md),
최신 진단은 [최신 인계](../treadding/REST-MIGRATION-HANDOFF.md)를 따른다.
2026-10-22 기존 결과는 READ_BEFORE 성공 후 QUOTE_WS 실패·주문 단계 미호출이다.
새 실패 원인 필드는 다음 실행부터 생기므로 과거 원인을 추정해 채우지 않는다.
이번 작업은 지정 PC 접근·예약 변경·실측 실행을 하지 않았다.

공유할 최소 결과:
- 실행일시 KST, 검사한 커밋, 지정 PC 여부, 모의 환경 여부.
- 조회 5건의 API 식별·complete/pages/행수·허용된 reason 코드.
- WS quotes_observed/fresh_before_close와 허용된 failure_stage/failure_kind.
- 주문 단계 호출 여부, ACK/REJECTED/UNKNOWN, 사후 연결 결과, HTS 미체결 확인 여부.
- Q01/Q02/Q08 확인/미확인과 근거 문서 위치. ACK는 체결 완료가 아니다.

키·토큰·계좌번호·원문 주문/체결번호·raw 응답·stderr는 제외한다.
결과가 없으면 PENDING이며 UNKNOWN은 재전송하지 않는다. 주문 실행 권한은 기존
승인 runner 범위를 넘겨 확대하지 않는다. 증거 기록 후에만 R04/R05 판정을 바꾼다.

## 4. 모바일 실기기 인수

[모바일 6항목 체크리스트](../D02-MOBILE-CHECKLIST.md)를 현행 보드에 맞춰 갱신했다.
iOS Safari, Android Chrome 각각 기종·OS·브라우저·접속 URL·커밋·확인자·시각과
6항목의 PASS/FAIL/NOT_RUN을 기록한다. 에뮬레이션/PC 창폭 확인은 대체 근거가 아니다.
민감한 값이 없는 합성 종목·패턴으로 확인한다. 화면 공유 시 개인 메모/링크를 가린다.

휴대폰의 localhost는 PC가 아니다. 같은 망의 검증용 PC에서 **web 디렉터리만**
서빙해 PC의 LAN IP로 접속하거나, 승인된 HTTPS 테스트 배포를 사용해야 한다.
LAN 연결 시 서비스 범위·방화벽을 담당자가 확인한다. 저장소 루트·환경파일은 서빙하지 않는다.
새 Origin에서는 기존 localStorage가 공유되지 않으므로 합성 백업으로 준비한다.
이 작업에서 외부 바인딩/방화벽/공개 배포를 변경하지 않았다.

## 담당자에게 받아야 할 최종 답변

1. 기존 서버 유무, 실제 저장소와 담당자, 승인된 OpenAPI 버전/파일.
2. 개발 base URL과 테스트 환경, 실제 인증 메타데이터·권한·CORS.
3. 이 계약안의 채택 또는 필드/오류/버전/멱등성 차이.
4. 클라우드 서비스·계정 소유자·지역·보존 기간·삭제/복구 기준.
5. 지정 PC R04/R05의 마스킹 결과와 두 모바일 기기의 실제 체크 결과.

비밀값은 받지 않는다. 이 패키지는 다른 사람에게 발송하지 않았으며 저장소에 인계한다.

## 이 패키지의 검증 기록

- OpenAPI: `openapi-spec-validator==0.7.2`로 3.0.3 문서 검증 PASS.
- `openapi-schema-validator`의 OAS30Validator로 합성 예시 10/10 스키마 검증 PASS.
  이는 서버 업무 규칙·HTTP·인증의 실제 통과 근거가 아니다.
- `node --test web/board/*.test.js`: 기존 웹 회귀 35 passed.
- `git diff --check`: PASS. 보드·브로커 실행 코드는 변경하지 않았다.
- 실제 API 호스트/인증/HTTP 테스트, 클라우드, 지정 PC 실증, 물리 모바일: 미검증.

OpenAPI 검증 재현(별도 개발용 Python 환경):

```powershell
python -m pip install openapi-spec-validator==0.7.2
python -m openapi_spec_validator docs/api/board-api.openapi.draft.json
```

개발 도구 설치는 키움 엔진 가상환경과 분리한다. 런타임 의존성을 추가하지 않았다.
