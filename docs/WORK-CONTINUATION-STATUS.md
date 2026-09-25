# CherryPulse-KR-01 개발 이어가기 기록

지정 Windows PC의 주문 없는 검사 및 향후 키움 읽기 전용 증거 수집 준비는
[키움 로컬 검증 안내](KIWOOM-LOCAL-VERIFICATION-GUIDE.md)에 정리했다.

- 기록일: 2026-09-24
- 확인한 GitHub `main`: `c38010d` (`Handle cross-symbol config command identity conflicts`)
- 이 기록의 목적: 대화가 중단되어도 현재 확인된 상태, 다음 작업 및 완료 판단 기준을 복원한다.
- 이 파일을 작성한 작업 공간에는 후속 **미커밋 변경**이 있을 수 있다. 재개 시 `git status`를 먼저 확인한다.
- 우선 기준: `AGENTS.md` → `docs/CherryPulse-KR-01-Development-Direction.md` → `docs/CherryPulse-KR-01-Rebuild-Plan.md` → `docs/REBUILD-02-CONTRACTS.md` → `docs/REBUILD-02-TEST-MATRIX.md` → `docs/REBUILD-02-OPEN-QUESTIONS.md`. 작업 순서는 `docs/NEXT-DEVELOPMENT-PLAN.md`를 따른다.

## 이번 대화에서 확인한 내용

1. GitHub `main`의 `c38010d`에는 D01 명령 ID를 같은 계좌·환경의 다른 종목에 재사용했을 때 명시적인 `CONFLICT_CONFIG_COMMAND_IDENTITY`로 처리하는 수정이 있다. 실제 원격 파일 내용을 확인했다.
2. 이 수정의 로컬 Linux Python 3.12 분리 검사에서 D01 관련 pytest **9 passed**, Ruff 및 `git diff --check`가 통과했다. Windows 3.10 32비트 전체 검사 또는 키움 검증 결과는 아니다.
3. 원격 커밋 `c38010d`는 이 작업 공간의 원래 로컬 커밋 `b478dc3`과 해시가 다르지만 해당 수정 파일의 내용은 일치한다. 로컬 작업은 원격 `main`의 트리를 기준으로 다시 시작해야 한다.
4. 현재 실제 주문 API 호출, 운영 DB 변경, 배포를 수행하지 않았다. D01~D10 전체 완료를 주장하지 않는다.

## 현재 상태와 다음 순서

| 단계 | 확인된 상태 | 다음에 필요한 작업 |
|---|---|---|
| D01 | 원하는 설정 수신·보관 및 로컬 가상 손절 규칙 저장은 존재한다. 인증과 적용 원장의 원자적 연결은 미완료 | 인증 경계와 desired/accepted/applied 상태 연결. `ACCEPTED`를 감시 활성화로 표시하지 않기 |
| D03 | 가상 손절 발동·보호 후보·요청별 의무와 조회·실패 후 재주문 차단 일부 구현 | 자동 시세 감시, 검증된 세션, 실제 조회·알림 및 남은 실행정책 검증. D03 완료로 간주하지 않기 |
| D02·D04~D10 | 비활성 보드와 종목 등록·편집·보관, 손절 패턴 초안 기능 일부 구현. 각 계획 완료 기준에는 미도달 | `docs/NEXT-DEVELOPMENT-PLAN.md`의 선행 관계와 단계별 기록에 따라 구현·검증 |

D02의 비활성 보드 골격은 `web/board/`에 추가했다. 브라우저 안에서만
저장되는 종목·손절 패턴 초안이며 모바일 실제 화면 검사는 아직 못 했다.
`docs/D02-BOARD-PROGRESS.md`를 확인하고 엔진 적용 상태와 혼동하지 않는다.

`New.stop_latch_version` 연결과 요청별 청산 의무 기록·조회가 현재 `main`에 존재한다. 최신 상세 범위와 남은 한계는 `docs/D03-VIRTUAL-STOP-PROGRESS.md`를 따른다. `UNKNOWN`은 조회 근거 없이 실패로 바꾸거나 재전송하지 않는다.

추가 단계에서는 요청별 `StopSellObligation`을 주문 요청과 한 트랜잭션에
기록하고 재시작·중복 요청·매도 부분체결 뒤에도 원래 연결이 유지되는지
검증했다. Linux 임시 fixture의 관련 pytest **10 passed**, Ruff 통과.
이 단계에서는 의무의 동적 잔량/완료 상태 조회, 취소·거절·`UNKNOWN`
대조, 자동 시세 감시와 검증된 거래 세션을 아직 완료하지 않았다.

후속 조회 단계에서는 원장 사실에서 의무별 부분체결·완료·미확정·거절
상태를 읽는 API를 추가했다. 이 상태 조회는 재주문 권한을 주지 않는다.
자동 시세 감시, 키움 조회 증거와 실제 세션, 거절·취소 이후 외부 조회·알림
연결은 여전히 남아 있다.

사용자 선택 1번을 반영해 가상 손절 매도 실패·거절 시 자동 재주문을
차단하는 기존 동작을 재시작까지 확인하고, 의무 조회에 다음 확인 행동
(`QUERY_BROKER`/`REVIEW_AND_ALERT`/`NONE`)을 추가했다. 관련 가상
pytest **11 passed**, Ruff와 공백 검사 통과. 상세 범위는
`docs/D03-VIRTUAL-STOP-PROGRESS.md`를 참고한다. 증권사 상태 조회,
알림 발송 및 미체결 판단 시간은 연결되지 않았다. 기존 보유분 편입 정책은
답변을 받지 않았으므로 원가·수량·규칙 인계가 확인될 때까지 차단한다.
이어서 기록된 거절·전송 실패 사유를 미완료 의무와 함께 읽도록 보완했다.
추가 가상 검사에서 관련 pytest **12 passed**, Ruff·공백 검사 통과.

## 2026-09-25 후속 진행

- 시작 기준: `main`의 `9d778df` (`origin/main`과 일치), 작업 시작 시 미커밋 변경 없음.
- D02에서 손절 패턴 초안을 덮어쓰지 않고 같은 계열의 다음 버전으로 저장하는 로컬 UI와 버전 비활성화를 추가했다. 이전 버전 연결은 유지하며 비활성 버전은 새 연결에 사용할 수 없다. 상세 동작은 [D02 진행 기록](D02-BOARD-PROGRESS.md)에 있다.
- `node --check web/board/board.js`와 `git diff --check` 통과. 브라우저·모바일 렌더링은 실행하지 않았다.
- 이 버전 기록은 브라우저 로컬 초안의 UX이며 D01 서버 계약·인증이나 엔진의 불변 설정 적용을 대신하지 않는다. 다음 작업은 실제 브라우저·모바일 확인 후 D01의 desired/accepted/applied 적용 경계를 안전하게 잇는 것이다. D03 자동 시세·세션, D04~D10 및 키움 실증은 별도 미완료다.

## 완료 조건과 차단 경계

- D01~D10의 세부 완료 기준은 `docs/NEXT-DEVELOPMENT-PLAN.md`와 `docs/DEVELOPMENT-GOAL.md`를 따른다. 문서 검사, Linux 가상 검사, Windows 검사, 키움 실증을 구별한다.
- 실제/모의 키움 주문 API, 운영 DB 변경, 배포는 별도 명시적 지시 및 지정 환경 확인 전에는 수행하지 않는다. 인증된 키움 조회 자료가 없는 상태에서 주문 필드와 세션 동작을 추정해 활성화하지 않는다.
- 거절·실패 후 자동 재주문 금지는 확정했다. 미체결 판단 시간, 기존 보유의 원가/규칙 인계, 키움 조회·체결의 식별자 의미는 근거와 사용자 결정이 없으면 차단 상태로 둔다. 그동안 가상 검증과 비활성 화면은 진행할 수 있다.
- 이 문서는 진행 상황의 기록이며 자동 백그라운드 실행이나 커밋·푸시 허가를 뜻하지 않는다. 작업 재개 시 `git status`, 원격 `main`, 관련 문서와 실제 테스트 결과를 다시 확인한다.

## 새 대화에서 사용할 요청

> CherryPulse-KR-01의 `AGENTS.md`, `docs/WORK-CONTINUATION-STATUS.md`, `docs/DEVELOPMENT-GOAL.md`, `docs/NEXT-DEVELOPMENT-PLAN.md`를 읽고 원격 `main` 및 로컬 변경을 확인한 뒤 D03의 가상 손절 의무와 매도 요청 연결부터 완료 조건대로 계속 진행해 줘. 매 단계에 실제 테스트 결과와 미검증 범위를 기록하고 다음 안전한 작업을 이어서 진행해 줘. 실제/모의 주문 API, 운영 DB 변경, 배포는 별도 명시적 지시 없이 수행하지 마.
