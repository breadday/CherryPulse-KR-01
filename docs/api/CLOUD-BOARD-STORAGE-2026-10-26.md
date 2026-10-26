# 보드 로그인·서버 저장 구현

## 범위와 실제 적용

대상 Supabase: `qrrrnxmsbrkqueaabjdr` (서울). 기존 Cloudflare Workers 보드의
로그인·종목·패턴·연결 저장을 구현했다. 사용자별 전체 초안 스냅샷 한 개를 저장한다.
이 기능은 엔진 설정 수락이나 시세·계좌·주문 동기화가 아니다.

- Supabase 실제 적용: `board_snapshot_storage` 마이그레이션 성공.
- 비공개 `cherrypulse_private` 스키마: `board_snapshots`, `save_receipts`.
- 공개 RPC: `cp_load_board`, `cp_save_board`. SECURITY INVOKER, 소유자 RLS,
  익명 역할 실행 권한 차단. service_role 키를 사용하지 않는다.
- 실제 DB에서 `supabase/tests/board_storage.sql`의 12개 assertion 통과.
  테스트용 사용자·스냅샷·저장 영수증은 같은 트랜잭션에서 모두 rollback했다.
- Supabase security advisors: 지적 0개.

## 웹·서버 계약

`GET /api/cloud-config`: 지정 프로젝트 URL·현행 publishable key·구현 capability.
이는 설정 조회이며 로그인이나 DB 저장 성공을 증명하지 않는다.

`GET /api/board`: 사용자 Bearer 토큰 필요. `{revision,snapshot,updatedAt}` 반환.
초안 없음은 `{revision:0,snapshot:null,updatedAt:null}`. 오류를 빈 초안으로 바꾸지 않는다.

`PUT /api/board`: 사용자 Bearer 토큰과 JSON
`{snapshot,expectedRevision,requestKey}`. 성공 `{revision,updatedAt}`.
전체 요청은 1 MiB 이하, 기존 전체 백업 스키마 v1로 링크·필드 검증한다.
수정은 DB 트랜잭션에서 사용자별 직렬화하고 revision을 증가시킨다.
같은 UUID·같은 내용·같은 기대 버전 재시도는 원래 응답을 반환한다.
키 재사용 내용 불일치는 409, 오래된 버전은 412, 검증 실패는 422,
사용자별 24시간 저장 영수증 1000개 한도 초과는 429다.
영수증은 24시간 후 다음 저장 시 정리한다. 정기 삭제 작업은 미구현이다.

기존 `/boards`·`/items`·`/patterns` OpenAPI는 개별 CRUD 계약안으로 남는다.
이번 `/api/board`는 원자적 전체 초안 저장 경로이며 계약안 구현 완료로 표시하지 않는다.

## 사용자 흐름

1. 보드의 **내 보드 서버 저장**에서 이메일·비밀번호로 새 보드 계정을 만든다.
   Supabase 대시보드 로그인과 별개다. 인증 메일이 요구되면 확인 후 로그인한다.
2. 서버 초안이 없으면 현재 브라우저 초안을 서버에 저장할 수 있다.
3. 기존 서버 초안이 있으면 서버 초안 확인 → 개수 확인 → 명시적 교체를 거친다.
   현재 초안이 필요하면 기존 전체 보드 백업을 먼저 다운로드한다.
4. 다른 기기 수정과 충돌하면 다시 불러오기 전 저장이 차단된다.
5. 저장 응답을 못 받으면 **미확인 저장 재시도**로 같은 요청을 재전송한다.
   그동안 로컬을 수정했다면 이전 저장 확인 후 새 내용을 다시 저장한다.

비밀번호·토큰은 파일/localStorage에 기록하지 않는다. 세션은 메모리에만 존재해
페이지 새로고침·종료 후 다시 로그인해야 한다. 자동 토큰 갱신은 미구현이다.
로그아웃은 이 세션의 refresh token을 폐기하도록 요청하지만 발급된 access token의
즉시 무효화를 보장하지 않는다. 접근 만료 시 다시 로그인해야 한다.
브라우저 초안은 로그아웃해도 남으므로 공유 기기에서는 JSON 백업 후 직접 정리한다.

## 배포와 남은 검증

`wrangler.jsonc`의 사용자 지정 URL과 공개 publishable key만 사용한다.
이 공개 키는 브라우저용이며 비밀 키가 아니다. 데이터 권한은 로그인·RLS가 결정한다.
Cloudflare 대시보드에 같은 이름 환경변수가 있으면 값이 이 설정을 덮어쓰는지 확인한다.

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run build
npx wrangler deploy
```

배포는 Cloudflare 계정에 인증된 환경에서 실행해야 한다. 이 세션에는 Cloudflare
배포 자격증명이 없으며, 운영 주소 `/api/cloud-config`는 구현 전 404였다.
따라서 이번 소스 반영을 운영 배포 완료로 간주하지 않는다.

미결: 운영 Worker 재배포와 URL 확인, 실제 이메일 인증·로그인 후 두 기기 저장 왕복,
Auth Site URL/메일 링크 목적지 설정, 이메일 발송 제한 및 필요시 SMTP 설정,
물리 iOS Safari·Android Chrome 인수. 계정 삭제/보존 정책 확정과 UI는 별도다.
R04/R05 지정 PC 실증·시세/계좌/주문·엔진 연결은 기존 미결 상태를 유지한다.

## 검증 기록

- `node --test cloud/worker.test.mjs web/board/*.test.js`: 54개 통과.
- `npm run build`: Wrangler 4.152.0 dry-run 성공.
- `node --check`: 보드·클라이언트 JS 통과. `git diff --check` 통과.
- 로컬 Python REST 검사는 pytest가 설치되지 않아 미실행. CI에서 확인한다.
- Wrangler 로컬 런타임은 호스트 `uv_interface_addresses` 오류로 실행되지 않았다.
  빌드 성공과 로컬/운영 Worker 실행 성공을 구별한다.
- 자동 브라우저 검사는 Chromium 실행 파일이 없고 다운로드가 유효한 ZIP을 반환하지
  않아 실행하지 못했다. 실제 화면·390px 레이아웃 통과로 표시하지 않는다.

2026-10-26: PR #17 코드 커밋 `682963e`의 GitHub Actions run `40323467969`에서
REST 오프라인 검사(Worker 빌드 포함)와 Windows 전체 회귀·가상 실행 모두 성공했다.
운영 Cloudflare 배포·실사용자 로그인 검증은 여전히 대기다.
