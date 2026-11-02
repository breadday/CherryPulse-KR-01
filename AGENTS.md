# CherryPulse-KR-01 개발 지침

2026-10-14 REST 전환의 최신 사용자 결정은 `docs/treadding/REST-MIGRATION-PLAN.md`를 먼저 읽는다.
중단·재개 시 `docs/treadding/REST-MIGRATION-HANDOFF.md`와 `docs/treadding/REST-MIGRATION-STATUS.json`을 확인하고 단계마다 갱신한다.
OpenCode로 자동 개발을 이어갈 때는 복사 가능한 실행 지시서 `docs/treadding/OPENCODE-AUTODEVELOPMENT-INSTRUCTIONS.md`도 따른다.
현재 사용자 요청은 계획·개발·검증·한글 커밋·push·CI 통과 후 반영을 포함한다. 주문 활성화와 구별한다.

개발 기준은 현재 REST 전환 문서를 다음 순서로 읽는다. 이전 계약·계획은 참고 자료이며 활성 개발 지시로 사용하지 않는다.

1. docs/treadding/REST-MIGRATION-PLAN.md
2. docs/treadding/REST-MIGRATION-STATUS.json
3. docs/treadding/REST-MIGRATION-HANDOFF.md
4. docs/treadding/REST-MIGRATION-VERIFICATION.md
5. docs/DEVELOPMENT-ENVIRONMENT.md

이전 개발방향·전환 계약은 `docs/reference/legacy-development/`에 보관한다.

- 사용자가 외부에서 찾은 종목을 등록하고 매수·매도 패턴을 연결하는 보드 기반 시스템으로 개발한다.
- 내부 종목 발굴·추천·전략 점수·성과 검증·후보 승인·일봉 후보 자동 편입을 새 기능으로 복원하지 않는다.
- back/은 기존 방식의 보관 자료다. 활성 모듈로 import하거나 기존 배치를 실행하지 않는다.
- 저장소 전용 스킬이나 과거 기록의 스윙·백테스트 승격 지침이 충돌하면 최신 개발방향과 사용자 요청을 우선한다.
- 손절·체결·중복 주문 방지·수량 대조·재시작 복구의 소프트웨어 검증은 유지한다.
- 사용자가 키움 모의 키를 환경변수 `KIWOOM_APP_KEY`/`KIWOOM_APP_SECRET`(도구 기본명 `CHERRYPULSE_PAPER_APP_KEY`/`SECRET`, 전자가 폴백)에 등록해 두었다. 키 값은 묻지 않고 환경변수에서 읽으며 파일·문서에 복사하지 않는다.
- 실제 주문·배포는 명시적 요청 없이 실행하지 않는다. 모의 계좌도 실제 주문 API를 호출할 수 있다.
- .env·계좌·토큰·운영 DB를 출력하거나 보관 문서에 복사하지 않는다.
- 사용자 변경을 보존하고 커밋·푸시는 별도 요청 시에만 한다.
- 문서 검산, 엔진 테스트, 증권사 확인, 배포 확인을 구별해 보고한다.
