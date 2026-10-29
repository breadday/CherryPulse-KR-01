# 헤르메스 자동 개발 지시서 — CherryPulse-KR-01

작성: 2026-10-29 KST. 대상: `breadday/CherryPulse-KR-01`.
사용자는 직장인으로 장중 수동 작업이 어렵다. 계속 진행하되 중단 시 다른 AI가
저장소 문서만으로 바로 재개할 수 있도록 작은 단위마다 기록한다.

## 사용 방법

헤르메스에서 이 저장소를 작업 대상으로 지정한 뒤 아래 한 문장을 입력한다.

> `docs/treadding/HERMES-AUTODEVELOPMENT-2026-10-29.md`를 읽고 지시대로
> 현황 확인부터 가능한 개발·테스트·문서화·한글 커밋·푸시·CI·main 반영까지
> 계속 진행해. 막힌 부분은 자동으로 해결 가능한 것부터 처리하고, 실제 PC나
> 사용자 조작이 필요한 부분은 필요한 증거와 다음 행동을 구체적으로 보고해.

## 1. 확인된 기준과 불확실한 항목

- 2026-10-29 원격 `main` 조회 기준 `b2d1e2f`에서 시작했다. 이 문서와
  후속 수정이 반영되면 SHA가 달라지므로 **현재 원격 HEAD를 다시 확인**한다.
- 2026-10-27 기록: 지정 PC의 `CherryPulse-R045-Demo`는 09:30 예약 실행으로
  확인됐고, `py -3.10`이 Python 3.10.8 32비트를 선택했다. 해당 인터프리터에
  `websockets==15.0.1` 설치 후 장외 연결 1회, 수신 시세 0을 확인했다.
  REST/WS 자체가 32비트를 요구하는 것은 아니다.
- 10월 28일 이후 예약이 실제 실행됐는지와 결과는 이 지시서 작성 환경에서는
  확인하지 못했다. 예약 상태·실행 결과·실제 주문 여부를 추정하지 않는다.
- 10월 27일 Chrome 검증 기록에서 삼성전자 005930 자동 입력과 삼성전자우
  005935 선택은 확인됐다. PIN 로그인 후 실제 저장·불러오기와 iOS/Android
  실기기 인수는 별도 증거가 필요하다. `/api/board` 스냅샷 경로가 있으며,
  `/boards`·`/items`·`/patterns` 개별 CRUD OpenAPI는 제안안이다.
- R04 `LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED`, R05 `DEMO_TOOL_OFFLINE_CI_ONLY`,
  R06 가상만, R07 미완료, R08 초안 UI/엔진 수락 미완료다. 실시간 시세 수신
  성공만으로 계좌 대조·주문·전체 자동매매 완료로 변경하지 않는다.
- `OPENCODE-AUTODEVELOPMENT-INSTRUCTIONS.md`의 옛 “PC 작업 없음” 설명 및
  이 지시만으로 commit/push 불허 문구는 이 날짜의 사용자 지시와 최신 인계보다
  오래됐다. 현장에서 더 최근의 사용자 지시와 증거를 우선한다.

## 2. 작업 시작: 현황·증거 먼저

1. 저장소 `AGENTS.md`, `REST-MIGRATION-PLAN.md`, `REST-MIGRATION-HANDOFF.md`,
   `REST-MIGRATION-STATUS.json`, `DEVELOPMENT-READY-AND-BLOCKERS.md`와 아래
   작업 관련 코드를 읽는다. 이전 날짜에 적힌 기록은 당시 사실로 취급한다.
2. `git status --short --branch`, `git branch --show-current`, `git log -5 --oneline`,
   `git fetch origin`과 로컬/원격 차이를 확인한다. 로컬 변경·다른 작업자의 파일을
   보존하며 무단 `reset`, `clean`, `stash`, 강제 push, 덮어쓰기를 하지 않는다.
   깨끗한 저장소의 main이 뒤처졌을 때만 `git pull --ff-only origin main`을 쓴다.
   충돌하면 무리해서 동기화하지 말고 기존 변경을 보존한 채 보고한다.
3. 작업 PC가 지정 PC인지 예약 작업의 이름·경로와 저장소 위치로 확인한다.
   다른 PC는 별도 환경이다. R045 작업 및 실행 결과는 **조회만** 한다.

```powershell
Get-ScheduledTask -TaskName 'CherryPulse-R045-Demo' -ErrorAction SilentlyContinue |
    Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName 'CherryPulse-R045-Demo' -ErrorAction SilentlyContinue |
    Select-Object LastRunTime, LastTaskResult, NextRunTime
Get-ChildItem .\results -Directory -Filter 'r045-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 5 | ForEach-Object {
        $manifestPath = Join-Path $_.FullName 'manifest.json'
        if (Test-Path $manifestPath) {
            $manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
            "날짜=$($manifest.day), 상태=$($manifest.status)"
            $manifest.steps | ForEach-Object {
                [pscustomobject]@{
                    단계 = $_.step; 종료코드 = $_.exit_code
                    사유 = $_.diagnostic.reason
                    수신시세수 = $_.diagnostic.quotes_observed
                    장마감전신선도 = $_.diagnostic.fresh_before_close
                    실패단계 = $_.diagnostic.failure_stage
                    실패종류 = $_.diagnostic.failure_kind
                }
            } | Format-Table -AutoSize
        }
    }
```

`results`가 없거나 manifest가 없으면 `미확인`으로 기록한다. 작업 스케줄러의
종료코드 0만으로 실증·주문 성공을 선언하지 않는다. 읽기와 WS 단계만의 근거로
주문 접수·체결·취소를 추정하지 않는다. 원문 로그와 주문번호·계좌번호·시세
원본·비밀번호·PIN·토큰·키는 출력/문서화/채팅 공유하지 않는다.

**예약 작업 주의:** 현재 `scripts/r045-morning-run.cmd`는 정규장 조건과 시세가
맞으면 모의 1주 지정가 제출을 시도하는 실증 runner를 호출한다. 이는 개발
자동화가 아니다. `orders_enabled=false`라는 문구만으로 이 runner가 주문을
절대 호출하지 않는다고 가정하지 않는다. 현행 예약이 여전히 등록·활성인지와
지난 주문/미체결 상태는 지정 PC 및 HTS에서 확인한다. 이 지시서 실행으로
runner 수동 실행, 예약 변경/재등록, 모의·실제 주문 또는 취소를 새로 승인한 것은
아니다. 미체결이 있을 수 있으면 사용자에게 HTS 확인을 안내한다. UNKNOWN은
자동 재전송하지 않는다. 주문 실증은 별도 명시된 범위와 실제 증거를 확인한다.

## 3. 독립 개발 순서 — 차단에 멈춰 서지 말 것

### A. 안전 수정과 최신 상태 확인

- `tools/r045_morning_run.py`와 `tests/rest/test_morning_run.py`를 검사한다.
  ORDER_PREVIEW 실패 시 ORDER_SUBMIT 호출이 중단되는지 확인한다.
  2026-10-29 코드 검토에서는 기존 코드가 미리보기 실패에도 제출 명령을
  호출할 수 있는 결함이 재현되어 차단 수정과 회귀 검사를 준비했다. 현재
  `main`에 그 수정이 있는지 먼저 확인하고, 없으면 합성 테스트로 재현 후
  `ORDER_SUBMIT`이 호출되지 않도록 고친다. 저장된 단계 목록·ABORTED·exit code를
  함께 검사한다. 실제 주문 호출로 테스트하지 않는다.
- R045 10/28 이후 저장된 manifest를 발견하면 단계·진단만 안전하게 요약한다.
  QUOTE_WS `quotes_observed>0` 및 `fresh_before_close=true`는 **WS 부분 근거**다.
  계좌 이력 식별, 주문·체결·취소, R04/R05 전체 완료는 각각의 증거가 있어야 한다.

### B. 다음 코드 작업: 실패 이유를 안전하게 인계

- `MorningRun._aborted_reason`이 현재 설정돼도 `_flush()`의 manifest에는
  직접 저장되지 않는지 소스를 먼저 확인한다. 결함이 존재하면 허용된 고정 코드만
  `abort_reason`으로 저장해 미리보기 실패·조회 실패·시세 파일 누락·가격 상한을
  구분하도록 구현한다. 기존 manifest 읽기 호환성을 유지한다.
- 임의 예외 메시지·stdout/stderr·원문 응답·계좌/주문번호·토큰은 저장하지 않는다.
  합성 fixture로 정상/실패·기존 manifest 호환·민감정보 비노출·실패 시 주문
  미호출을 검증한다. 이미 수정됐거나 더 우선인 버그가 확인되면 중복 구현하지
  말고 증거를 기록하고 다음 독립 작업으로 넘어간다.

### C. 보드 사용자 경험과 인수

- 사용자가 보고한 종목명·금액 입력 문제, 화면 폭 및 다음 개장 날짜 설정을
  실제 최신 코드와 사용자/재현 근거로 확인한다. 기존 보드 초안·백업·PIN 접속을
  보존하면서 재현 가능한 UI 결함부터 개선한다. 시장 휴일은 추정하지 말고
  확인 가능한 거래일 자료/기존 계약이 없으면 자동 설정을 `미확정`으로 표시한다.
- 종목 등록 → 이름 검색 및 코드 자동 입력 → 패턴 연결 → 미리보기 → PIN 로그인 →
  명시적 서버 저장 → 다른 기기 불러오기를 검증한다. 서버 초안의 교체 확인과
  버전 충돌 보호를 유지하며 실제 사용자 자료를 무단 삭제/덮어쓰지 않는다.
- 실제 인증/서버 저장 왕복은 사용자 조작 또는 승인된 테스트 환경에서 검증하고,
  모바일 iOS Safari·Android Chrome은 실제 기기 결과를 별도 기록한다. 테스트의
  합성 데이터는 합성으로 표시한다. 코드 검사만으로 물리 기기 인수로 표시하지 않는다.

### D. 이어서 할 일

- R04 이력 식별·조회 완전성, 주문 접수와 체결 구분, Q01/Q02/Q08 근거를
  `REST-R04-LIVE-PROBE-CHECKLIST-2026-10-21.md`에 따라 확인한다.
  R05 dispatcher·보호 연결·실주문 활성화는 해당 근거와 명시된 운영 승인 전에
  열지 않는다. 주문 테스트에 대한 접근이 막혀도 문서·합성 테스트·오프라인
  오류 처리 등 독립 작업은 계속 진행한다.
- 내부 종목 추천·점수·백테스트 승격을 만들지 않는다. 이 프로젝트는 사용자가
  외부에서 찾은 종목과 매수·매도 패턴을 관리한다. `back/`을 활성 import하지 않는다.

## 4. 자동 실행·검증·인계 규칙

각 단위를 **계획 → 구현 → 관련 테스트 → 상태/HANDOFF 기록 → 한글 커밋 →
푸시 → CI → main 반영** 순서로 수행한다. 사용자가 이 흐름을 반복 작업으로
요청했다. 작업 전 이미 존재하는 다른 변경은 커밋 범위에 섞지 않는다.
코드의 테스트가 실패하면 고치거나 실패 원인을 명확히 남기고 main에 강제
병합하지 않는다. 원격 접근이 안 되면 안전한 커밋과 정확한 재개 명령을 남긴다.

```powershell
py -3.10 tools/verify_rest_migration.py
node --test cloud/worker.test.mjs web/board/*.test.js
git diff --check
```

실행 가능한 환경에서 관련 테스트를 먼저 실행하고, 전체 Windows 엔진 검사는
CI 또는 Windows에서 확인한다. 실제 브로커/실제 사용자 계정/운영 DB나 WebSocket
호출이 필요한 테스트는 그 실행 권한과 환경을 확인한 뒤 별도 증거로 기록한다.
`REST-MIGRATION-STATUS.json`과 `REST-MIGRATION-HANDOFF.md`에 변경 파일,
실행 명령·결과, 아직 안 된 것, 막힌 이유, 다음 명령을 남긴다. `orders_enabled`
등 기존 안전 설정을 임의로 변경하지 않는다.

Cloudflare 보드 배포는 접근 가능한 승인된 배포 환경에서 명시된 범위로 실행하고,
소스 병합·배포·실제 화면 인수를 구분한다. 새로운 외부 서비스·유료 리소스·
실계좌 주문 활성화는 사용자 지시가 없는 한 진행하지 않는다.

컨텍스트/시간 제한으로 중단될 때는 진행 중 변경을 안전하게 보존하고 마지막
통과 검사, 미완료와 정확한 재개 지시를 기록한다. 자동화는 에이전트 세션이
실행 중일 때의 연속 작업이며, 세션이 종료됐는데도 계속 실행된다고 주장하지 않는다.

## 5. 마지막 보고

한국어로 ① 완료한 기능과 변경 파일 ② 테스트·CI 결과 ③ 커밋/푸시/main·배포
상태 ④ 미확인 사항과 원인 ⑤ 사용자에게 필요한 최소 조작을 보고한다.
지정 PC 상태나 broker 실행을 직접 확인하지 않았다면 확인했다고 쓰지 않는다.
