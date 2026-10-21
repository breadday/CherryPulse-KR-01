# R04/R05 정규장 실증 체크리스트 — 2026-10-21 작성

정규장(09:00~15:20 KST)에 지정 PC에서 한 번에 실행할 수 있도록 흩어진
명령·판정 기준을 모은 실행 체크리스트다. 이 문서 자체는 상태를 바꾸지 않고
주문을 보내지 않는다. 실증 결과 기록 전까지 R04/R05 상태와
`can_reconcile=false`, 주문 OFF는 유지한다.

근거 문서: [R02 인증·읽기](REST-R02-AUTH-READONLY.md),
[R03 WebSocket](REST-R03-WEBSOCKET.md),
[R04 조회 근거](REST-R04-QUERY-EVIDENCE.md),
[R05 주문 실증](REST-R05-ORDER-DEMO.md),
[오픈 질문 Q01/Q02/Q08](../REBUILD-02-OPEN-QUESTIONS.md).

## 0. 사전 준비물 — 장 시작 전 확인

- [ ] 지정 Windows PC이고 `py -3.10-32 -c "import sys; print(sys.version)"`가
      3.10.x 32bit를 출력한다.
- [ ] 모의 전용 `CHERRYPULSE_PAPER_APP_KEY`/`CHERRYPULSE_PAPER_APP_SECRET`가
      `setx`로 사용자 환경에 저장돼 있다. 새 셸을 열어 값 출력 없이
      `[bool]$env:CHERRYPULSE_PAPER_APP_KEY` 등으로 존재만 확인한다.
      파일·명령줄·문서에 키를 두지 않는다.
- [ ] 모의 계좌와 키움 OpenAPI+ 모의 호스트 접근이 가능하다. 이전 3회 실측과
      달리 이번에는 **주문 1건 뒤에 이력 행을 관찰하는 것이 목적**이다.
- [ ] HTS(영웅문) 접속: 미체결 확인·취소와 현재가 확인에 필요하다.
- [ ] 날짜·시간이 정규장(09:00~15:20)이고 휴장이 아니다. 장 시작 직후 변동성
      회피를 원하면 09:30 이후 실행도 유효하다.
- [ ] `results/` 폴더에 어제 날짜 센티널(`paper-buy-<어제>.json`)만 있어
      오늘 제출이 막히지 않는다. 센티널은 날짜별 1회 제한이다.

안전 경계: 이 체크리스트의 주문은 R05 도구 1주 지정가 1회뿐이다. 자동
재시도·취소·원장 연결은 없다. UNKNOWN 결과는 재시도 금지이며 기록하고 중단한다.
원문·토큰·계좌번호를 출력·저장하지 않는다. 도구 보고서는 이미 마스킹돼 있다.

## 1. 예열 — 키 미사용 오프라인 확인

```powershell
py -3.10-32 -m tools.probe_kiwoom_rest
```

- 판정: exit 0, `EXECUTION_NOT_REQUESTED`. 네트워크·키 미사용.

## 2. R04 읽기 실측 — 읽기 전용 5건

```powershell
py -3.10-32 -m tools.probe_kiwoom_rest --execute-read-only --max-pages 3 --include-history
```

- 판정: exit 0, 5건(`kt00018/ka10075/kt00007/kt00009/ka10076`) 전부
  `complete:true`, `reason:QUERY_COMPLETE_ONLY`, 각 쿼리 pages·observed_rows 기록.
- 주문 전 빈 계좌면 `observed_rows:0`이 정상이다. 이 단계는 연결·입력 승인·
  페이지 완전성 확인이며 식별 증거는 주문 후 5단계에서 얻는다.
- `complete:false`나 `SETUP_OR_AUTH_UNCONFIRMED`면 토큰·환경을 점검하고
  결과를 기록한 뒤 주문 단계로 넘어가지 않는다.

## 3. R05 미리보기 → 제출 — 1주 지정가 1회

HTS 현재가를 확인한 뒤(Q12 상한 10만원 이하, 예: 삼성전자 005930):

```powershell
py -3.10-32 -m tools.submit_paper_buy --symbol 005930 --price <HTS 현재가>
py -3.10-32 -m tools.submit_paper_buy --symbol 005930 --price <HTS 현재가> --confirm-execute
```

- 미리보기 판정: exit 0, `EXECUTION_NOT_REQUESTED`.
- 제출 판정: exit 0, `ORDER_ACKED`. 거절은 `broker_code`와 마스킹 메시지 확인.
  - `broker_code: 20`(모의투자 종료) → 장 밖 실행이므로 정규장에 재제출한다.
    거절이라 센티널은 재시도를 막지 않는다.
  - `TRANSPORT_UNKNOWN` → 재시도 금지. HTS에서 접수 여부를 확인하고 결과를
    기록한 뒤 세션을 끝낸다. `SECOND_ORDER_BLOCKED`면 오늘 제출은 끝났다.
- 제출 직후 HTS에서 미체결 1주를 확인한다. 체결되지 않은 미체결은
  **HTS에서 직접 취소**한다. 자동 취소 도구는 없다.

## 4. WebSocket 실측 — 장중 수신

```powershell
py -3.10-32 -m tools.probe_kiwoom_ws 005930 --seconds 30 --execute-read-only
```

- 판정: exit 0, `quotes_observed > 0`, `fresh_before_close: true`.
- 실패 보고는 `SETUP_OR_STREAM_UNCONFIRMED` 하나뿐이다. 상세 원인 추정을
  문서에 적지 않고 재실행 1회까지 확인한다.

## 5. 이력·연결 확인 — 주문 후 재조회

제출한 주문이 접수됐으면(미체결이든 체결이든) 이력 TR에 행이 생긴다.

```powershell
py -3.10-32 -m tools.probe_kiwoom_rest --execute-read-only --max-pages 3 --include-history
py -3.10-32 -m tools.verify_paper_linkage --execute-read-only
```

- 연결 판정: `LINKAGE_CONSISTENT`면 Q01 근거(동일 주문번호가 2곳 이상 일치)와
  원주문 연결 청결이 확인된다. `LINKAGE_UNCONFIRMED`면 관측 사실만 기록한다.
- 이력 판정: `observed_rows > 0`인 쿼리에 대해 6절 양식으로 관측 사실을 남긴다.
  값은 도구 보고서 범위(개수·불리언·필드 존재)로 기록하고 원문·계좌번호·
  주문번호는 문서에 두지 않는다.
- 체결이 관측됐으면 `kt00009 cntr_no` 유일성, `ka10076 cntr` 행 구조,
  누적/단위 수량 힌트를 비교한다. 체결이 없으면 Q02는 미확정 유지다.

## 6. 판정 기준 — 상태 갱신 조건

| 관측 | 판정 | 후속 조치 |
|---|---|---|
| 2~4단계 전부 성공, 주문 접수, 이력 행 0건 | R04 실증 부분 완료. Q01은 `LINKAGE_CONSISTENT` 시에만 부분 확정 | 상태는 결과 기록 후 사용자 확인을 거쳐 갱신. Q02/Q08 미확정 유지 |
| 체결까지 관측, 이력 3건 행·체결번호 비교 가능 | Q01/Q02/Q08 식별 근거 확보 시도 | `can_reconcile`은 식별 매핑 확정 전까지 false 유지 |
| UNKNOWN 또는 이력·연결 불일치 | 실증 실패로 기록 | R04/R05 상태 변경 없음. 차단 사유를 증거 문서에 남김 |

- 상태 JSON 갱신은 **증거 기록 후에만** 하고 `known_baseline`은 건드리지 않는다.
- R05→R06 이후(R05 dispatcher, R06 연결, R07 무인, R08 엔진 인수)는 여전히
  실측 근거 확정과 별도 운용자 승인 뒤에 착수한다.

## 7. 결과 기록 위치

- R04 증거: `REST-R04-QUERY-EVIDENCE.md` 끝에 날짜 섹션 추가(아래 양식).
- R05 결과: `REST-R05-ORDER-DEMO.md`에 날짜 섹션 추가.
- 검증 요약: `REST-MIGRATION-VERIFICATION.md`에 명령·exit code 요약 추가.
- 상태: `REST-MIGRATION-STATUS.json`의 R04/R05 값과 `next_action`을
  증거와 일치하게 갱신. `HERMES-TASK-2026-10-19-RESULT.md` TASK-2 진행도 함께
  표기한다.

증거 양식(복사해 사용):

```markdown
## 정규장 실측 — <YYYY-MM-DD HH:MM>, 지정 PC

- 명령: <사용한 명령 5줄>, exit code: <각 줄>
- 조회: 5건 complete/rows/pages/reason 요약(원문·계좌번호 없음)
- 주문: <ORDER_ACKED | 거절 코드 | UNKNOWN>, 센티널 파일 존재
- WS: quotes_observed=<n>, fresh_before_close=<bool>
- 연결: <LINKAGE_CONSISTENT | LINKAGE_UNCONFIRMED | 미실행>
- Q01/Q02/Q08: <각 항목 확정·부분·미확정과 근거 필드>
- 미확정 유지 항목과 다음 행동: <한 줄>
```
