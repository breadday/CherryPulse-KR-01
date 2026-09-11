# TASK-027 계좌 설정 안전 검증 명세

## 목표

키움 연결 전에 계좌 설정 오류를 fail-closed로 차단한다. 모의투자 기본 흐름은 유지하고, 주문 허용 모드에서 계좌번호 누락이나 잘못된 형식으로 로그인하지 않도록 한다.

## 계약

- 주문 허용 모드에서 `ACCOUNT_NO`가 비어 있으면 `RuntimeError`를 발생시킨다.
- 설정된 계좌번호는 정확히 10자리 숫자여야 한다.
- 검증은 `CommConnect()` 호출 전에 수행한다.
- 계좌번호 값과 비밀번호는 로그·테스트 출력·문서에 기록하지 않는다.
- 모의투자에서 계좌번호가 비어 있는 경우 기존 로그인 계좌 fallback은 유지한다.
- `GetLoginInfo("GetServerGubun")`이 기대 서버와 다르면 계좌 조회 전에 차단한다.
- 기대 서버 설정은 `KIWOOM_EXPECTED_SERVER`이며 기본값은 `paper`다.
- 기대 서버가 `live`이면 `KIWOOM_LIVE_CONFIRMATION=I_UNDERSTAND_LIVE_TRADING`을 요구한다.

## 범위

- `broker/kiwoom_broker.py`
- `tests/test_task027_live_account_guard.py`
- 운영 현황 및 테스트 증거 문서

실제 키움 로그인, 계좌 조회, 주문 전송은 실행하지 않는다.
