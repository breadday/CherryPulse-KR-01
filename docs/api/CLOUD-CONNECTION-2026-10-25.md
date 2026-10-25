# Cloudflare·Supabase 연결 준비

사용자가 제공한 주소를 역할에 맞게 정리했다.
- Cloudflare: https://cherrypulse-kr-01.breadday99.workers.dev/board/
- Supabase: https://qrrrnxmsbrkqueaabjdr.supabase.co

## 실제 확인과 차단

2026-10-25 연결된 Supabase 앱의 프로젝트 목록에 대상 ref가 없었다.
대상 ref에 대한 get_project도 권한 오류로 실패했다. 다른 프로젝트는 조사·변경하지 않았다.
따라서 대상 테이블/권한/Auth 설정/공개 키를 확인하지 못했고 DB를 변경하지 않았다.
이 자료는 해당 프로젝트가 없거나 고장났다는 진단이 아니다. 현재 앱 연결의 접근 한계다.

필요한 사용자 작업: Supabase 앱을 **해당 프로젝트를 볼 수 있는 계정/조직으로 연결**한다.
비밀번호·토큰·secret/service_role 키를 채팅에 제공할 필요는 없다.
연결 후 담당 AI가 get_project → list_tables → get_publishable_keys를 확인하고,
기존 스키마와 권한에 맞게 로그인·CRUD·RLS를 설계/구현/검증한다.
목록에 다른 프로젝트가 나온다고 그 프로젝트를 대신 사용하지 않는다.

## 이번에 구현한 소프트웨어 단위

- `wrangler.jsonc`: 사용자 Worker 이름, `cloud/worker.mjs`, 정적 자산 `./web`만 배포.
  사용자가 준 주소는 Pages의 pages.dev가 아니라 **Workers의 workers.dev**이므로
  Pages 전용 설정 대신 Workers Static Assets 경계로 준비했다.
- `/api/cloud-config`: 지정 프로젝트 URL과 현대 publishable 키 형식만 공개하는 설정 확인.
  설정 누락/다른 URL/지원하지 않는 키는 503. 임의 env·Secret key·legacy JWT는 반환하지 않는다.
  `configurationReady`는 환경값 준비 의미이며 실제 Supabase 접근·로그인 통과를 뜻하지 않는다.
- 인증/CRUD/엔진 capability는 모두 false. 미구현 `/api/*`는 JSON 404로 닫는다.
  정적 HTML 200으로 API 성공을 가장하지 않는다. 쓰기는 405로 거부한다.
- 보드에서 버튼을 누를 때만 같은 Origin의 설정 API를 확인한다. 키값을 표시·저장하지 않는다.
  localStorage 초안·패턴·실제 엔진·계좌·주문·예약 작업은 변경하지 않았다.

## 배포 담당자 설정 (미실행)

Cloudflare의 해당 Worker 런타임 변수:
- `SUPABASE_URL`: wrangler.jsonc의 지정 URL과 같아야 한다.
- `SUPABASE_PUBLISHABLE_KEY`: 해당 Supabase 프로젝트의 `sb_publishable_...` 공개 키.
  기존 legacy anon 키는 이 경계에서 지원하지 않는다. Secret/service_role을 넣지 않는다.

실제 배포에는 Wrangler 및 Cloudflare 계정 권한이 필요하다. 이번에는 설치·로그인·
배포를 실행하지 않았으며 CLI 버전은 배포 단계에서 공식 문서 확인 후 고정한다.
GitHub 연결 배포가 있다면 빌드 설정과 실제 배포 SHA도 따로 확인해야 한다.
프로젝트 환경값은 배포 시 dashboard/승인된 비밀 저장 경로에 직접 넣는다.
정적 `python -m http.server ...`로는 Worker API가 제공되지 않아 설정 확인이 404일 수 있다.
이 결과를 DB 장애로 기록하지 않는다.

## 검증

`node --test cloud/worker.test.mjs web/board/*.test.js`: 43 passed (기존35 + 신규8).
설정 미비 실패, 비밀 키 비노출, API 정적 페이지 폴백 방지, web만 게시,
설정 완료를 로그인 완료로 오인하지 않는 표시를 검사했다.
GitHub CI에서도 신규 8개를 실행하도록 추가했다. `git diff --check` 통과.
Workers 실제 런타임·배포 URL·Supabase Auth·DB·사용자별 RLS는 미검증이다.

## 다음 구현

대상 계정 연결 → 현행 스키마 확인 → 확정 API 계약 기준의 DB/RLS·인증·CRUD →
보드 로그인·서버 저장·복원 → 실제 배포/사용자별 접근 검증 순서다.
현재 변경은 연결 준비 단계이며 이 다음 기능을 완료했다고 보고하지 않는다.
