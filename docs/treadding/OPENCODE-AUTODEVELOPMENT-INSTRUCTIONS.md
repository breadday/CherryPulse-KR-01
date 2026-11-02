# OpenCode 자동 개발 지시서

갱신일: 2026-11-02
대상 저장소: `CherryPulse-KR-01`

저장소 `AGENTS.md`와 사용자의 최신 직접 지시를 따른다. 과거 개발 문서는 `docs/reference/legacy-development/`에 보관된 참고 이력이다. 활성 개발은 REST API·WebSocket 중심으로 한다.

## 시작 전

1. 아래 문서를 순서대로 확인한다.
   - `AGENTS.md`
   - `docs/treadding/REST-MIGRATION-PLAN.md`
   - `docs/treadding/REST-MIGRATION-STATUS.json`
   - `docs/treadding/REST-MIGRATION-HANDOFF.md`
   - `docs/treadding/REST-MIGRATION-VERIFICATION.md`
   - `docs/DEVELOPMENT-ENVIRONMENT.md`
2. `git status --short --branch`, 현재 branch, 최근 기록을 확인한다. 기존 변경은 사용자 작업으로 보존하며 reset, clean, stash, 무단 덮어쓰기·삭제를 하지 않는다.
3. 상태 JSON, 코드, 실제 테스트 결과가 다르면 차이를 기록하고 사실을 재확인한다.

## 개발 경계

- REST HTTP와 WebSocket 계약을 기준으로 한다. `back/` 및 `docs/reference/legacy-development/`는 보관 자료이며 활성 모듈로 가져오거나 실행하지 않는다.
- 종목 발굴·추천·점수화·백테스트 승격·자동 후보 편입을 복원하지 않는다. 보드는 사용자가 외부에서 찾은 종목과 기존 매수·매도 패턴을 연결하는 흐름을 유지한다.
- 주문 안전장치(중복 방지, 체결·수량 대조, 미확정 결과 재전송 금지, 손절, 재시작 복구)를 약화하지 않는다.
- `orders_enabled=false`를 유지한다. 실제/모의 주문 API 호출, 취소, scheduler 실행·활성화·변경, 운영 DB 변경, 배포는 별도 명시 승인이 있어야 한다.
- 실제 증권사 응답, 계좌 식별, 장중 시세, 주문 결과, 클라우드 인수 및 기기 인수를 합성 테스트로 대신하거나 완료 처리하지 않는다.
- `.env`, 키, 토큰, 계좌번호, 운영 DB나 원문 브로커 응답을 출력·기록하지 않는다. 비밀값은 환경변수에서만 읽는다.

## 구현·검증 절차

1. 상태 JSON의 미완료 gate를 코드 증거와 비교해 가장 작은 독립 작업을 정한다.
2. 영향 파일과 테스트를 먼저 확인하고, 계약을 추측하지 않는다.
3. 변경 후 다음 로컬 검사를 수행한다. Python은 `.venv-rest`의 Python 3.15 환경을 사용한다.

```powershell
.venv-rest\Scripts\python.exe -m pytest -q --tb=short
.venv-rest\Scripts\python.exe tools\verify_rest_migration.py
node --test cloud/worker.test.mjs web/board/*.test.js
npm run build
```

4. 정확한 명령, exit code, 테스트 수, 실패·미실행 범위를 기록한다. `git diff --check` 및 최종 Git 상태도 확인한다.
5. 의미 있는 단계마다 `REST-MIGRATION-STATUS.json`과 `REST-MIGRATION-HANDOFF.md`를 실제 증거로 갱신한다. `orders_enabled=false`와 외부 차단 상태를 유지한다.
6. 커밋·push는 사용자가 명시적으로 요청했을 때에만 해당 작업 변경을 선별해 수행한다. CI는 push 후 원격 결과를 확인하고 로컬 검증과 구분한다.

## 결과 보고

한국어로 간결하게 완료한 작업·파일, 실제 검증 결과, 문서 상태, 미검증 외부 항목, 다음의 정확한 단계를 보고한다. 완료하지 않은 CI·계좌·주문·배포 상태를 완료로 표현하지 않는다.
