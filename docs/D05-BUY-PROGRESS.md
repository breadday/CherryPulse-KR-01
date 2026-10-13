# D05 매수 가상 시나리오 진행 기록

- 기준: Q12 확정 13건(`REBUILD-02-Q12-DECISION-QUESTIONNAIRE.md`), Q12 매수 계약(`REBUILD-02-CONTRACTS.md`), QB 문서 시나리오(`REBUILD-02-TEST-MATRIX.md`)
- 상태: **가상 검증 부분 구현**. 실주문·실시세·감시 활성화가 아니다.

## 2026-10-12 일반 매도 정책 확정

사용자가 다음 일반 매도 정책을 확정했다. 손절 정책과 별도이며 매수 Q12를
변경하지 않는다.

- 평균 매수가 대비 목표수익 +5%, +10%는 알림 단계다. 일반 매도는 사용자가
  직접 제출하며 목표 도달을 주문 자동 트리거로 쓰지 않는다. 당일 15:10
  시간 알림은 1회다.
- 수량 기본은 전량, 부분 매도는 50% 단위다. 매도 후 남은 보유 수량의 기존
  손절 규칙을 유지한다. 짝수 수량에서 50% 산정은 정수이며, 홀수 수량은
  임의 반올림을 금지하고 부분 선택을 막는다(전량은 허용).
- 지정가가 기본이고 가격은 제출 직전 최근 체결가다. 시장가는 확인 팝업 뒤
  명시 제출한다. 당일 유효, IOC/FOK 금지.
- 60초 미체결이면 취소 요청 후 수동 검토한다. 자동 재주문하지 않는다.
  취소 확정 전 예약을 유지하며 UNKNOWN은 주문·체결·잔고 대조 전 차단한다.
- 손절 보호가 일반 매도보다 우선한다.

수익률은 확인된 평균 매수가 대비 최근 체결가 변화로 해석한다. 수수료·세금
포함 순수익 기준은 아직 확인되지 않았으므로 UI에서 실현 순수익처럼 표시하지
않는다. +5/+10 알림의 재발송 억제 단위도 미정이라 영속 dedupe 연결 전에는
외부 알림을 활성화하지 않는다.

보드 UI, 명시적 매도 제출 핸들러, 알림 상태 저장,
15:10 스케줄러, 알림 중복 억제 상태, Telegram 호출자/실패 기록, 키움 주문 경계는 아직 구현되지 않았다. Telegram 공용 송신 어댑터는 마련했으나 D05 알림에 연결하지 않았다. 순수
가상 경계 `contracts/sell_evaluation.py`는 목표수익 가격 관측과 명시적 수동
매도 선택의 안전 검사만 수행하며 원장 명령/dispatcher 호출을 만들지 않는다.
부분 수량 계산은 홀수일 때 차단한다. 사용자가
일반 매도 정책을 승인한 것은 실/모의 주문 API 실행 권한이 아니다.

## 2026-10-12 거래일 경계와 만료 전달

매수 체결 사실 `Fill.trading_date`에 명시적 거래일을 보관하고,
`Ledger.filled_buy_qty_on(symbol, trading_date)`가 해당 날짜의 확인된 매수 체결량을
원장에서 계산하도록 했다. 체결 수신 시각을 거래일로 추정하지 않는다. 날짜가 없는
기존 매수 체결이 있으면 `BUY_FILL_TRADING_DATE_UNKNOWN`으로 전체 날짜량 계산을
차단한다. 호출자는 이를 `filled_today_qty=None`으로 평가기에 전달해
`BUY_DAY_EVIDENCE_INCOMPLETE`로 신규 매수를 막아야 한다. 기존 자료를 자동
소급 변환하지 않는다.

QB 시나리오 매수 명령에 Q12 만료 시각(15:20)을 `New.expires_at`으로 전달하도록
보강했다. 기존 `Ledger.submit` 및 `VirtualDispatcher.send`는 각각 요청 저장 시점과
전송 직전에 현재 시각으로 만료를 검사하므로 만료 후 제출/전송을 거절한다.
반복 명령은 기존 멱등 결과를 반환하며 새 만료로 기한을 연장하지 않는다.

일반 매도는 별도 계약 경계를 추가했다. 조건·수량·가격/세션·미체결 정책이
결정되기 전까지 비활성 초안만 허용하며 평가/주문을 만들지 않는다. 보호 손절
우선, 기존 예약·미확정 상태 및 수량 대조 검사를 공통 선행 조건으로 둔다.
세부 사용자 선택은 `PROJECT-STATUS-AND-DECISIONS.md` 질문서에 남아 있다.

검증은 실행하지 않았다. 실제 키움, 운영 DB, Supabase 연결/RLS 적용, 외부 알림,
실/모의 주문, 배포도 수행하지 않았다.

## D05 확장: 당일 재진입·만료 강제 — 2026-10-11

평가기에 당일 누적 체결량(`filled_today_qty`)과 명시 만료(`expires_at`,
세션 끝 `session_end`)를 필수 입력으로 추가했다. 보유 Short-circuit 다음으로
전량 청산 뒤 0 보유에서도 당일 체결 이력이 있으면 `DAY_REENTRY_BLOCKED`로
차단한다(Q12 4.1). 거래일은 체결 사실에 명시해 원장에서 조회한다. 만료가 없거나 timezone이 없으면 `EXPIRY_REQUIRED`, 이미
지났으면 `COMMAND_EXPIRED`, 세션 끝을 넘으면 `EXPIRY_BEYOND_SESSION`이다
(Q12 2.2/2.3). QB1은 원장 사실에서 구한 당일 누적량으로 보유 차단을
재확인했고, 만료·재진입은 평가기 경계 5종으로 검증했다.

- 검증: 신규 포함 `tests/test_virtual_buy_qb.py` **4 passed**, 전체 pytest
  **181 passed, 4 subtests passed** (`7.83s`), 관련 파일 Ruff check·format
  통과. 첫 린트 21건(포맷·반환 수·인자 수·naive 시각)은 포맷 적용과 헬퍼
  분리(`_standing`·`_market`), 명시 8인자 `noqa` 근거 표기, 선례대로
  `replace(tzinfo=None)`로 해소했다. `git diff --check` 통과. 키움·운영 DB·
  배포는 실행하지 않았다.

## QB1·QB2 가상 구현 — 2026-10-11

`contracts/buy_evaluation.py`에 Q12 첫 버전 전용 순수 평가기를 추가했다.
주문을 만들거나 전송 허가를 내지 않는다. 확인된 값만 사용한다: 고정 1주,
10만원 상한, 보유 시 미평가 후 차단(Q12 4.2/6.2), 신선한 최근 체결가와
`last_price <= target` 비교. 보유 차단이 시세 검사보다 먼저이며, 전량 청산
후 당일 재진입(보유 0 상태의 날짜 추적)은 다루지 않고 호출자 측 명령 검토에
남긴다. 명령 만료 15:20은 `New.expires_at`으로 전달하고 저장/가상 전송에서
재검사한다.

`tests/test_virtual_buy_qb.py`에 기존 원장·dispatcher 계약만으로 QB1·QB2를
재현했다. 새 전송 경로나 주문 API를 추가하지 않았다.

- QB1: 평가 CANDIDATE → 매수 지정가 1주 제출·전송·접수 → 체결 1주 →
  `StopRuleAssignment` 1건(버전 2)·관리 1·평균가 70000·원가 근거
  (1, 70000, 2) → 동일 키 재제출 멱등(호출 0 추가) → 보유 1 상태에서
  재평가 `HOLDING_BLOCKS_BUY`로 제출 자체를 안 함(요청·호출 0 추가) →
  재생 무변경. 최종 주문 `1=0+1+0`.
- QB2: 평가 CANDIDATE → 제출·전송·접수 → 미체결 상태에서 취소 1주 제출·
  전송·확정 → 주문 `1=0+0+1`, 관리 0 → `recover()` 빈 결과, 종결 요청
  재전송 거부, 요청·호출 추가 0 → 재생 무변경. 60초 경과는 호출자 주도
  서사로 두고 원장에 시각을 조작하지 않았다.
- 평가기 경계: 목표가 초과·동일가·2초 경계 신선·3초 지연·미래 시세·시세
  없음·종목 불일치·10만원 상한 경계·비정상 목표가·보유 시 낡은 시세에도
  보유 차단 우선, 17개 케이스.

## 검증

Windows Python 3.10.8 32비트(지정 PC 설치):

```text
tests/test_virtual_buy_qb.py::test_qb1_buy_fill_assigns_protection_and_blocks_same_day_rebuy PASSED
tests/test_virtual_buy_qb.py::test_qb2_unfilled_buy_cancels_without_reorder PASSED
tests/test_virtual_buy_qb.py::test_buy_evaluator_blocks_without_holdings_or_stale_evidence PASSED
3 passed in 0.23s
```

- 관련 파일 Ruff check 통과, Ruff format check 통과(2 files already formatted).
- 전체 pytest **180 passed, 4 subtests passed** (`7.84s`, 기존 177 + 신규 3).
- `python -m execution` 가상 데모 정상 종료.
- `git diff --check` 통과. 키움 로그인·주문/조회, 운영 DB, 배포는 실행하지 않았다.

## 남은 D05 조건

- 거래일별 매수 체결 조회와 주문 저장/전송 만료 검사는 가상 경계에 연결했다.
  남은 것은 브로커 원문 거래일 매핑, 거래소 세션 확인, D01 인증된 명령과의
  연결이다(모두 미구현).
- 자동 시세·검증 세션(D03), 키움 읽기 근거(D06), 실제 주문 경계(D07),
  물리 모바일(D02)은 계속 차단·대기다.
