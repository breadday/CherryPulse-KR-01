# R05 — 모의 1주 지정가 매수 실증 도구, 사용자 실행 전

2026-10-14, `feature/rest-r05-order-demo`. 주문 API 호출은 이 문서의 도구를
사용자 PC에서 직접 실행할 때만 일어난다. 개발 과정에서는 어떤 주문도 내지 않았다.

## 규격

`kt10000` 주식 매수주문, `POST /api/dostk/ordr`(모의 호스트 고정).
필수 `dmst_stex_tp/stk_cd/ord_qty/trde_tp`, 선택 `ord_uv/cond_uv`.
응답 최상위의 `ord_no`·`dmst_stex_tp`와 `return_code`를 확인한다.
구현 코드는 공식 예제를 복제하지 않았고 필드명만 참고했다.

## Q12 제한 내장

- 지정가만 가능하고 수량은 1주 고정이다. 시장가·다른 수량을 표현할 수 없다.
- 가격은 10만원 상한의 양수 소수 문자열이다.
- 같은 날 두 번째 제출은 센티널이 막는다. 거절은 재시도 가능, UNKNOWN은 차단이다.
- 자동 재시도·주문 수정·취소·원장 연결은 없다.

## 도구

- `tools/submit_paper_buy.py`: 기본 미리보기(키·네트워크 미사용).
  `--confirm-execute`와 모의 전용 환경변수 2개가 있어야 1회만 전송한다.
  보고서는 주문번호·토큰·계좌번호를 포함하지 않는다.
  거절 시 브로커 코드와 마스킹된 메시지를 보여준다.
- `tools/verify_paper_linkage.py`: 이력 3건+미체결을 읽어 주문번호 집합 일치,
  원주문 연결 청결, 체결 관측 여부만 불리언으로 보고한다. 식별자 원문은 출력하지 않는다.

## 실증 순서와 판정

1. 미리보기: `--symbol 005930 --price <HTS 현재가>` → exit 0, `EXECUTION_NOT_REQUESTED`.
2. 제출: 같은 명령에 `--confirm-execute` → exit 0, `ORDER_ACKED`.
3. 연결 확인: `verify_paper_linkage --execute-read-only` → `LINKAGE_CONSISTENT`면
   Q01(동일 번호 2곳 이상 일치)과 원주문 청결이 확인된다.
4. `fills_seen`은 지정가 특성상 false일 수 있다. Q02 체결번호는 체결 관측 뒤에 확정한다.

미체결 1주는 HTS에서 직접 확인·취소한다. 자동 취소 도구는 이번 범위가 아니다.
