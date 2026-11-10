# R05 — 모의 1주 지정가 매수 실증 도구와 결과

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

## 배치 실행과 예약

- `run-paper-demo.bat [price] [symbol]`: 미리보기·제출·연결 확인을 순서대로
  실행하고 바탕화면 로그에 저장한다. 키는 프로세스 환경에서만 읽고 값을
  표시·저장하지 않는다. CMD 호환 문법·CRLF 유지, `echo` 문구에 괄호 사용 금지.
- `run-paper-demo.bat check [symbol]`: 제출 없이 연결 확인만 한다.
- 예약 작업에는 `run-paper-demo.bat [price] [symbol] nopause`를 등록한다.
  키는 `setx`로 사용자 환경에 한 번만 저장하고 명령줄·파일에 두지 않는다.
  예약 실행도 날짜별 센티널 1회 제한을 따르므로 매일 최대 1주문이다.
  미체결 누적·가격 고정은 예약을 등록한 사람이 HTS와 함께 관리한다.

미체결 1주는 HTS에서 직접 확인·취소한다. 자동 취소 도구는 이번 범위가 아니다.

## 첫 실증 결과 — 2026-10-14 저녁, 사용자 PC

`403870` 1주 지정가 `56600` 제출은 전송됐으나 `broker_code: 20`,
`broker_message: 모의투자 종료`로 거절됐다. 인증·POST·응답 판정·거절 보고
경로는 끝까지 동작했고, 거절이라 센티널 없이 재시도가 가능하다.
모의투자 시간 종료가 원인이라 장중(정규장 시간)에 같은 명령으로 재제출한다.

## 실제 모의 주문 — 2026-11-06 12:51~12:58 KST

- 사용자가 모의 주문 실행을 요청한 뒤, 예약 작업이 비활성(`Disabled`)이고 당일 sentinel이 없는 것을 확인하고 승인된 R045 runner를 한 번 실행했다: `tools.r045_morning_run --symbol 067310 --price-cap 36800`.
- 사전 REST 5건은 모두 complete, 각 1 page였다. 보유 1행은 미매핑으로 남겼고 `account_reconciled=false`다. WebSocket은 1 connection, 24 quotes, malformed 0, fresh before close true.
- 주문 결과: `ORDER_ACKED`, PAPER, 1주 지정가, 가격 `24700`. `results/paper-buy-20261106.json` sentinel은 `ACKED`다. 주문번호·계좌번호는 이 문서에 기록하지 않는다.
- 사후 linkage runner는 실수로 기본 종목 `005930`을 조회했다. 이 호출은 `LINKAGE_UNCONFIRMED`였고, 이 결과로 주문 결과를 판정하지 않았다. 올바른 종목 `067310`으로 별도 읽기 전용 재조회한 결과는 `ka10076` 행 1건, 기타 세 테이블 0건, 주문번호 다중 일치 false, 집합 일치 false, 원주문 연결 청결 false, 체결번호 확인 false, 최종 `LINKAGE_UNCONFIRMED`였다.
- 따라서 주문 접수만 확인됐고 미체결/체결 여부는 확정하지 않는다. HTS에서 해당 모의 주문을 확인해야 한다. 자동 재주문·수정·취소는 하지 않았고, 사용자 확인 전 다시 주문하지 않는다. `account_reconciled=false`, `can_reconcile=false`, `orders_enabled=false` 유지.
- 원인 수정: `tools/r045_morning_run.py`가 linkage 조회에 runner 종목을 전달하도록 수정했고, 사후 history/linkage 검사 실패 시 manifest를 `PARTIAL_POST_ORDER_CHECKS_UNCONFIRMED`로 남기게 했다. TDD 회귀 테스트에서 기존 동작이 실패한 뒤 수정했으며 REST runner 테스트 10개 통과.

## HTS 사용자 확인 — 2026-11-09

- 사용자가 제공한 **[0343] 기간별 주문체결상세** 캡처에서 2026-11-06의 067310 지정가 매수 1주가 접수됐고, 체결량 1주·평균체결가 24,700·체결시각 12:54:35(KRX)로 표시됨을 확인했다.
- 후속 **[0341] 실시간 미체결** 캡처는 종목 필터 067310, 전체 조건이며 조회 완료 후 결과 행이 없었다. 따라서 캡처 조회 시점에는 067310 미체결 주문이 표시되지 않았다.
- **[0351] 금일주문체결내역** 캡처도 비어 있었지만 이는 조회 당일 목록이므로 11/06 과거 체결의 증거로 사용하지 않는다.
- 판정: HTS가 주문 접수 및 1주 체결, 캡처 시점의 미체결 없음이라는 사용자 화면 근거를 제공한다. 다만 REST 이력과의 API linkage/Q01 다중 일치는 여전히 `LINKAGE_UNCONFIRMED`; R04의 계좌 identity mapping과 원장 대조도 미완료다.
- 추가 주문·정정·취소·브로커 조회는 하지 않았다. `orders_enabled=false`, `account_reconciled=false`, `can_reconcile=false` 유지.

## 2026-11-10 로컬 linkage 판정 및 진단 보존 개선

- 저장된 `results/r045-20261106/manifest.json`의 최상위 `DONE`은 과거 실행기 산출물이다. 같은 manifest의 `LINKAGE` 단계는 exit 1과 `LINKAGE_UNCONFIRMED`를 기록하므로 성공적인 linkage로 해석하지 않는다. 원본 결과 파일은 증거 보존을 위해 수정하지 않았다.
- 저장된 요약은 `ka10076` 행 1건, 나머지 세 이력/미체결 query 행 0건, `order_seen_in_multiple=false`, `order_sets_equal=false`, `orig_link_clean=false`다. 검증기는 최소 두 query의 주문 집합이 있어야 교차 확인으로 보고, 원주문 참조가 있으면 원주문 연결이 깨끗하다고 판정하지 않는다. 따라서 저장 증거상 미확정 사유는 다중 query 교차 근거 부족 및 원주문 연결 조건 미충족이다. 어떤 응답 차이로 이 상태가 생겼는지는 raw 행을 저장하지 않았으므로 알 수 없다.
- 자동 분석의 안전성을 높이기 위해 현재 R045 runner가 향후 linkage manifest에 고정된 네 query의 행 수·고유 주문 수와 판정 bool만 보존하도록 개선했다. 원문 주문번호·계좌·토큰·응답·stderr는 allowlist에 포함하지 않는다.
- 회귀 검증: `tests/rest/test_order_demo.py`와 `tests/rest/test_morning_run.py` 집중 실행 `23 passed`; 실제 브로커 조회·주문·정정·취소·재전송은 하지 않았다.
- 이후 실행 결과가 추가되더라도 linkage/account reconciliation을 자동 승격하지 않는다. `LINKAGE_UNCONFIRMED`, `account_reconciled=false`, `can_reconcile=false`, `orders_enabled=false`를 유지한다.
