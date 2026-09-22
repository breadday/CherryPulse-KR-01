# CherryPulse-KR-01

사용자가 등록한 종목에 매수·매도 패턴을 연결하고, Windows 엔진이 조건 감시·주문·체결·손절을 처리하며 웹 보드에서 상태를 확인하는 시스템으로 개편 중입니다.

현재 **내부 SQLite 원장과 가상 실행 검사**, **Vue mock 트레이딩 보드 1차 화면**, **Python·TypeScript 공통 계약 1차 구현**, 그리고 **손절 우선 가상 실행 흐름**을 완료했습니다. 요청 중복 방지, 예약, 부분체결, 취소 UNKNOWN, 지연 체결, 실패·거절, Windows 계좌 잠금, 재시작 차단, 전송 직전 매수 중지와 손절 이후 진입 차단·확인 수량 청산을 검사합니다. 웹 보드와 공통 fixture는 예시 데이터만 사용하며 실제 증권사 어댑터와 연결되지 않았습니다.

- [자동화 개발 계획](docs/AUTOMATION-DEVELOPMENT-PLAN.md)
- [STEP 00 보안·개발 기준선](docs/AUTOMATION-STEP-00-BASELINE.md)
- [STEP 01 Vue Mock 트레이딩 보드](docs/AUTOMATION-STEP-01-WEB-BOARD.md)
- [STEP 02 공통 계약과 API 경계](docs/AUTOMATION-STEP-02-CONTRACTS.md)
- [STEP 03 손절 우선 실행 흐름](docs/AUTOMATION-STEP-03-STOP-LOSS.md)
- [STEP 04 매수·일반 매도 패턴](docs/AUTOMATION-STEP-04-PATTERNS.md)
- [STEP 05 동기화와 실제 보드](docs/AUTOMATION-STEP-05-SYNC.md)
- [STEP 06 모의환경 검증 경계](docs/AUTOMATION-STEP-06-PAPER.md)
- [개발방향](docs/CherryPulse-KR-01-Development-Direction.md)
- [전면 개편 계획](docs/CherryPulse-KR-01-Rebuild-Plan.md)
- [조회 완전성 근거·다음 작업](docs/REBUILD-04-QUERY-EVIDENCE.md)
- [가상 체결 격리·재처리](docs/REBUILD-04-QUARANTINE.md)
- [수량 불일치 대조 해소](docs/REBUILD-04-RECONCILIATION.md)
- [미전송 의도 폐기](docs/REBUILD-04-DISCARD.md)
- [명령 만료·적용 버전](docs/REBUILD-04-COMMAND-FRESHNESS.md)
- [요청 실패·계좌 잠금 기록](docs/REBUILD-04-REQUEST-FAILURES-AND-LOCK.md)
- [내부 원장 1차 구현 기록](docs/REBUILD-04-LOCAL-LEDGER.md)
- [실행 계약](docs/REBUILD-02-CONTRACTS.md)
- [12개 검증 시나리오](docs/REBUILD-02-TEST-MATRIX.md)
- [미확인 사항](docs/REBUILD-02-OPEN-QUESTIONS.md)
- [개발 환경과 검사 명령](docs/DEVELOPMENT-ENVIRONMENT.md)
- [기존 파일 보관 기록](docs/REBUILD-01-ARCHIVE.md)

가상 데모는 프로젝트 루트에서 실행합니다. 매번 임시 DB를 사용하며 로그인·실제 주문 API를 호출하지 않습니다.

```powershell
& .\.venv\Scripts\python.exe -m execution
```

기존 선정·전략 평가·스윙 실행 방식은 `back/legacy-2026-09-13/`에 보관했습니다. 보관본은 참고·복구용이며 활성 모듈에서 import하지 않습니다. 영구 삭제하지 않았습니다.
