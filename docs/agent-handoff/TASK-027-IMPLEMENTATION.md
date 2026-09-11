# TASK-027 IMPLEMENTATION

## 변경 내용

- `KiwoomBroker.connect()`에서 로그인 시작 전에 계좌번호를 정규화한다.
- 주문 허용 모드의 계좌번호 누락을 차단한다.
- 명시된 계좌번호가 10자리 숫자가 아니면 차단한다.
- `paper` 모드의 계좌 목록 fallback 동작은 유지한다.
- 계좌번호 안전 경계와 현재 운영 상태를 문서화했다.

## 안전성

- `CommConnect()` 및 `SendOrder()`는 테스트에서 호출하지 않았다.
- 계좌번호·비밀번호·Telegram 자격증명은 증거 문서에 기록하지 않았다.
