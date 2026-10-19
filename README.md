# CherryPulse-KR-01

사용자가 등록한 종목에 매수·매도 패턴을 연결하고, Windows 엔진이 조건 감시·주문·체결·손절을 처리하며 웹 보드에서 상태를 확인하는 시스템으로 개편 중입니다.

현재 **내부 SQLite 원장과 가상 실행 검사**를 구현했습니다. 요청 중복 방지, 예약, 부분체결, 취소 UNKNOWN, 지연 체결, 실패·거절, Windows 계좌 잠금, 재시작 차단과 전송 직전 매수 중지를 검사합니다. REST 조회·WebSocket 관측 경계와 브라우저 초안 보드를 구현했습니다. 실제 주문 dispatcher·원장·보호 연결은 계좌 실증 대기입니다.

- [개발방향](docs/CherryPulse-KR-01-Development-Direction.md)
- [남은 개발 작업 계획과 착수 순서](docs/NEXT-DEVELOPMENT-PLAN.md)
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

## 메인 보드 실행

프로젝트 루트에서 실행한 뒤 **http://localhost:8080/** 을 엽니다.

```powershell
python -m http.server 8080 --bind 127.0.0.1 --directory web
```

메인 진입점은 `web/index.html`, 실제 화면은 `web/board/index.html`입니다.
종목·손절·매수 패턴 초안과 설정 현황을 확인할 수 있습니다.
초안은 같은 브라우저·주소의 로컬 저장소에 저장됩니다. 기존에 사용하던 주소와 포트를 유지하세요.
실제 보유·주문은 미조회이며 감시·주문은 비활성입니다. 클라우드 배포·엔진 동기화는 미완료입니다.

종목 카드의 **상세·설정**에서 매수·손절 패턴을 각각 연결하고 가상 가격으로 조건을 미리 확인할 수 있습니다. 미리보기는 실제 시세·보유·감시 상태가 아니며 주문을 생성하지 않습니다. 전체 백업에는 매수 연결도 보존됩니다. 복원 시 최신 코드를 사용하세요.
