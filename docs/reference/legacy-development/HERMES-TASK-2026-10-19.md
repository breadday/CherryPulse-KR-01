# HERMES TASK - CherryPulse-KR-01 보드 재구성 및 REST 마이그레이션 R04 게이트

> 작성일: 2026-10-19 / 요청자: bread / 기준 커밋: 1ec7966 / 현재 브랜치: main
> 관련 문서: AGENTS.md, docs/D02-BOARD-PROGRESS.md, docs/treadding/REST-MIGRATION-STATUS.json, docs/treadding/MAIN-BOARD-LAYOUT-2026-10-19.md

## 0. 목적
CherryPulse-KR-01의 화면을 보드 기반으로 재구성하고, REST 마이그레이션 R04 게이트를 통과시킨다. 현재 PC 보드는 6/6 Pass이나 엔진 미연결 상태이며, 루트 엔진 파일이 사라지고 문서 경로 불일치가 있다.

## 1. 현재 상태 요약 (검증 완료)

### 1.1 보드 UI (D02)
- 위치: `web/board/board.js`, `board-backup.js`, `board.test.js`
- 상태: Node 23 passed, pytest 180 passed, PC Chrome localhost:8000 실클릭 6/6 Pass
- 구현됨: `crypto.randomUUID` 폴백 `newDraftId()`, 토글 44px min-height, 매수 패턴 폼 Q12 (kind BUY_PRICE_AT_OR_BELOW, 10만원 초과 차단)
- 미진행: 물리 모바일(iOS/Android) 실기기 검증 PENDING, `엔진 미연결` 유지, 서버 동기화(D01/D08) 대기
- 브랜치: `feature/board-layout-20261019`, `feature/board-pattern-preview` 존재

### 1.2 REST 마이그레이션
- STATUS.json: current_task=R04, next_action="정규장 시간에 모의 1주 지정가 재제출·연결 확인 후 Q01 게이트 확정"
- R00 DOCUMENTED / R01 OFFLINE_VERIFIED_ACCOUNT_UNVERIFIED / R02 OFFLINE_VERIFIED_ACCOUNT_UNVERIFIED / R03 OFFLINE_VERIFIED_LIVE_UNVERIFIED / R04 LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED / R05 DEMO_TOOL_OFFLINE_CI_ONLY / R06 VIRTUAL_ONLY_REST_UNCONNECTED / R07 TODO / R08 BOARD_DRAFT_LINK_PREVIEW_VERIFIED_ENGINE_ACCEPTANCE_PENDING
- 검증 명령: `python tools/verify_rest_migration.py` (또는 `py tools/verify_rest_migration.py`)
- 문서 위치: `docs/treadding/`에 8개 존재 (HANDOFF, STATUS, VERIFICATION, R02~R05 등)

### 1.3 경로 불일치
- `AGENTS.md`는 `REST-MIGRATION-HANDOFF.md`를 루트에서 찾으나 실제 위치는 `docs/treadding/REST-MIGRATION-HANDOFF.md`
- 루트 필수 파일 미존재: `main_live.py`, `engine.py`, `config_live.py`, `broker/kiwoom_broker.py` → `back/` 아카이브로 이동된 것으로 추정. `back/`은 활성 import 금지(AGENTS.md 규정)

## 2. 헤르메스에게 시킬 작업

### TASK-1: 문서 경로 정합성 수정 (우선순위: P0, 10분)
- [ ] `AGENTS.md`의 `REST-MIGRATION-HANDOFF.md` 경로를 `docs/treadding/REST-MIGRATION-HANDOFF.md`로 수정
- [ ] `AGENTS.md`의 루트 필수 파일 체크 로직에서 `main_live.py` 등 4개가 `back/`에 있으면 정상으로 간주하도록 예외 처리, 또는 해당 항목을 DEPRECATED로 표기
- [ ] `docs/treadding/REST-MIGRATION-STATUS.json`의 `known_baseline` 유지
- 검증: `py check.py` 실행 시 미진행으로 뜨지 않아야 함

### TASK-2: R04 LIVE_EMPTY_ACCOUNT_IDENTITY_UNVERIFIED 게이트 통과 (P0)
- [ ] `tools/verify_rest_migration.py` 실행 환경 점검 (REST는 Python 3.10.8 이상·3.11 미만에서 32/64비트 모두 가능. 32비트는 별도 OCX/COM 검사 때만 필요)
- [ ] 모의계좌 읽기, WebSocket 장중 수신, 허용된 주문·체결·취소 실증 로그 수집
- [ ] 정규장(09:00~15:20) 시간에 모의 1주 지정가 재제출 테스트 수행
- [ ] 결과로 `docs/treadding/REST-MIGRATION-STATUS.json`의 R04를 `LIVE_VERIFIED`로 업데이트, `verification_command` 결과 첨부
- 산출물: `docs/treadding/REST-R04-QUERY-EVIDENCE.md`에 증거 캡처

### TASK-3: 보드 엔진 연결 - R08 해소 (P1)
- [ ] `REBUILD-02-CONTRACTS.md` 기준으로 `/boards`, `/items`, `/patterns` API 계약 확인
- [ ] `web/board/board.js`의 `commitDraft` 흐름을 브라우저 초안 → REST API 호출로 전환
  - 현재: `kind BUY_PRICE_AT_OR_BELOW`, `orderType LIMIT` 고정, 브라우저에만 저장, `미적용·엔진 미연결` 표시
  - 목표: `POST /boards/{id}/items`, `POST /patterns` 호출, 엔진 연결 시 `미적용` 해제
- [ ] `board-backup.js`의 허용 kind에 매수 kind 포함 상태 유지 확인
- [ ] Node 테스트 23 passed 유지, 신규 API 호출 모킹 테스트 추가 (목표 28 passed)
- 산출물: `web/board/board.js` 수정 + `web/board/board.test.js` 추가

### TASK-4: 모바일 실기기 검증 체크리스트 6/6 (P2)
- [ ] LAN IP `http://172.17.32.1:8000` 또는 지정 PC IP로 배포
- [ ] iOS Safari, Android Chrome 실기기에서 D02 체크리스트 재수행:
  1) 100001 차단 문구 2) 70000 저장·카드·detail 3) 손절 select 매수 제외 4) 토글 비활성/재활성 5) 백업 JSON에 매수 kind 포함 6) 390×844 가로 스크롤 없음
- [ ] `docs/D02-BOARD-PROGRESS.md`에 실기기 결과 기록, `pending` 해제

## 3. 금지 사항
- `back/` 폴더 활성 import 금지 (`from back`, `import back`)
- 키움 실제 주문·조회·운영 DB·배포는 `AGENTS.md` 명시된 지정 PC에서만
- `.env`, `*.sqlite3`, `*.db` 커밋 금지
- 보안 컨텍스트 의존 코드 금지 (`crypto.randomUUID` 단독 사용 금지, `newDraftId()` 폴백 유지)

## 4. 완료 조건 (Definition of Done)
- [ ] `py check.py`에 ❌ 미진행 0건
- [ ] `REST-MIGRATION-STATUS.json` R04 = LIVE_VERIFIED, R08 = ENGINE_ACCEPTANCE_VERIFIED
- [ ] `node --test web/board/board.test.js` 28+ passed
- [ ] `python -m pytest` 180+ passed (기존 baseline 유지)
- [ ] 모바일 실기기 6/6 Pass 로그 첨부

## 5. 참고 명령어
```bat
py check.py
py -c "import pathlib; print(pathlib.Path('docs/treadding/REST-MIGRATION-STATUS.json').read_text(encoding='utf-8'))"
node --test web/board/board.test.js
python tools/verify_rest_migration.py
```

---
이 문서를 읽고 TASK-1부터 순서대로 수행하고, 각 TASK 완료 시 커밋 메시지에 `HERMES TASK-2026-10-19 - TASK-n` 포함할 것.
