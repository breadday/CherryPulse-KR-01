# TASK-027 IMPLEMENTATION

## 변경 내용

- `KiwoomBroker.connect()`에서 로그인 시작 전에 계좌번호를 정규화한다.
- 주문 허용 모드의 계좌번호 누락을 차단한다.
- 명시된 계좌번호가 10자리 숫자가 아니면 차단한다.
- `paper` 모드의 계좌 목록 fallback 동작은 유지한다.
- `GetServerGubun`을 확인해 기대 서버와 다른 환경의 계좌 사용을 차단한다.
- `KIWOOM_EXPECTED_SERVER` 기본값은 `paper`다.
- 기대 서버가 `live`인 경우 정확한 승인 문자열 없이는 `CommConnect()`를 호출하지 않는다.
- 계좌번호 안전 경계와 현재 운영 상태를 문서화했다.

## 안전성

- `CommConnect()` 및 `SendOrder()`는 테스트에서 호출하지 않았다.
- 계좌번호·비밀번호·Telegram 자격증명은 증거 문서에 기록하지 않았다.
