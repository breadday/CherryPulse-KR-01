# D05 매수 가상 시나리오 진행 기록

- 기준: Q12 확정 13건(`REBUILD-02-Q12-DECISION-QUESTIONNAIRE.md`), Q12 매수 계약(`REBUILD-02-CONTRACTS.md`), QB 문서 시나리오(`REBUILD-02-TEST-MATRIX.md`)
- 상태: **가상 검증 부분 구현**. 실주문·실시세·감시 활성화가 아니다.

## D05 확장: 당일 재진입·만료 강제 — 2026-10-11

평가기에 당일 누적 체결량(`filled_today_qty`)과 명시 만료(`expires_at`,
세션 끝 `session_end`)를 필수 입력으로 추가했다. 보유 Short-circuit 다음으로
전량 청산 뒤 0 보유에서도 당일 체결 이력이 있으면 `DAY_REENTRY_BLOCKED`로
차단한다(Q12 4.1). 날짜 경계 리셋은 호출자 측 세션 책임이며 원장에 날짜를
새기지 않았다. 만료가 없거나 timezone이 없으면 `EXPIRY_REQUIRED`, 이미
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
남긴다. 명령 만료 15:20 값은 계약·매트릭스에 기록된 대로 두고, 가상 제출에는
`expires_at`을 생략했다(만료 검사는 `check_freshness` 계약과
`test_command_freshness.py`에서 별도 검증됨).

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

- 위 확장으로 당일 재진입·만료 강제의 평가기 강제까지 완료했다. 남은 것은
  날짜 경계 리셋과 만료의 제출 시점 강제를 포함한 세션·동기화 연결, D01
  인증된 명령과의 연결이다(모두 미구현).
- 자동 시세·검증 세션(D03), 키움 읽기 근거(D06), 실제 주문 경계(D07),
  물리 모바일(D02)은 계속 차단·대기다.
