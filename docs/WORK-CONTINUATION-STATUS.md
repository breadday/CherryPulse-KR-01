# CherryPulse-KR-01 개발 이어가기 기록

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
| D01 | 원하는 설정의 계약·수신과 가상 규칙 저장은 각각 존재한다. 다른 종목의 명령 ID 충돌 수정 반영 | 인증된 명령 수락과 로컬 적용의 상태 및 원자적 경계 설계·검증. `ACCEPTED`를 감시 활성화로 표시하지 않기 |
| D03 | 가상 손절 발동 영속화, 신선도 2초, 정규장이라고 입력한 가상 시장가 매도 예약 존재 | 손절 의무와 개별 매도 요청의 명시적 추적, 중복·부분체결·재시작·추가 매수 체결 시 수량 검증. 실제 세션 확인과 자동 시세 연결은 별개 |
| D02·D04~D10 | 계획 문서의 완료 기준에 도달했다고 확인하지 못함 | `docs/NEXT-DEVELOPMENT-PLAN.md`의 선행 관계대로 구현·검증·결과 기록 |

D02의 비활성 보드 골격은 `web/board/`에 추가했다. 브라우저 안에서만
저장되는 종목·손절 패턴 초안이며 모바일 실제 화면 검사는 아직 못 했다.
`docs/D02-BOARD-PROGRESS.md`를 확인하고 엔진 적용 상태와 혼동하지 않는다.

후속 로컬 변경으로 `New.stop_latch_version`을 통한 발동 기록과 가상 매도 요청의 연결을 추가했다. Linux 임시 fixture에서 D03 관련 pytest 9개, Ruff, `git diff --check`가 통과했다. 상세한 검증 범위는 `docs/D03-VIRTUAL-STOP-PROGRESS.md`에 있다. 이 연결은 독립 청산 의무 원장과 1:1 수량 추적을 완성하지 않는다. 다음 작업에서는 기존 매도 예약·부분체결·추가 매수 체결·취소 `UNKNOWN`의 의무 수량과 요청을 명시적으로 대조하고, 재시작 시 같은 의무의 중복 전송을 차단한다. `UNKNOWN` 요청은 조회 근거 없이 실패로 바꾸거나 재전송하지 않는다.

추가 단계에서는 요청별 `StopSellObligation`을 주문 요청과 한 트랜잭션에
기록하고 재시작·중복 요청·매도 부분체결 뒤에도 원래 연결이 유지되는지
검증했다. Linux 임시 fixture의 관련 pytest **10 passed**, Ruff 통과.
이 단계에서는 의무의 동적 잔량/완료 상태 조회, 취소·거절·`UNKNOWN`
대조, 자동 시세 감시와 검증된 거래 세션을 아직 완료하지 않았다.

후속 조회 단계에서는 원장 사실에서 의무별 부분체결·완료·미확정·거절
상태를 읽는 API를 추가했다. 이 상태 조회는 재주문 권한을 주지 않는다.
자동 시세 감시, 키움 조회 증거와 실제 세션, 거절·취소 이후 실행 정책은
여전히 남아 있다.

## 완료 조건과 차단 경계

- D01~D10의 세부 완료 기준은 `docs/NEXT-DEVELOPMENT-PLAN.md`와 `docs/DEVELOPMENT-GOAL.md`를 따른다. 문서 검사, Linux 가상 검사, Windows 검사, 키움 실증을 구별한다.
- 실제/모의 키움 주문 API, 운영 DB 변경, 배포는 별도 명시적 지시 및 지정 환경 확인 전에는 수행하지 않는다. 인증된 키움 조회 자료가 없는 상태에서 주문 필드와 세션 동작을 추정해 활성화하지 않는다.
- 미체결·거절 후 대응, 기존 보유의 원가/규칙 인계, 키움 조회·체결의 식별자 의미는 근거와 사용자 결정이 없으면 차단 상태로 둔다. 그동안 가상 검증과 비활성 화면은 진행할 수 있다.
- 이 문서는 진행 상황의 기록이며 자동 백그라운드 실행이나 커밋·푸시 허가를 뜻하지 않는다. 작업 재개 시 `git status`, 원격 `main`, 관련 문서와 실제 테스트 결과를 다시 확인한다.

## 새 대화에서 사용할 요청

> CherryPulse-KR-01의 `AGENTS.md`, `docs/WORK-CONTINUATION-STATUS.md`, `docs/DEVELOPMENT-GOAL.md`, `docs/NEXT-DEVELOPMENT-PLAN.md`를 읽고 원격 `main` 및 로컬 변경을 확인한 뒤 D03의 가상 손절 의무와 매도 요청 연결부터 완료 조건대로 계속 진행해 줘. 매 단계에 실제 테스트 결과와 미검증 범위를 기록하고 다음 안전한 작업을 이어서 진행해 줘. 실제/모의 주문 API, 운영 DB 변경, 배포는 별도 명시적 지시 없이 수행하지 마.
