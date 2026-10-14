# R04 — 조회 근거 경계 준비, 실제 원장 연결 전

2026-10-14. `adapters/kiwoom_rest_evidence.py`는 실행 원장을 import하지 않는다.

구현: 명시적 앱/계좌 별칭, 조회 전후 timezone-aware 시각, 로컬 이벤트 revision,
개별 조회 완전성, 중복 종류, 범위 불일치, 조회 구간 중첩과 구간 사이 revision 변경 검사.
이 metadata는 계좌 실체 확인이나 가상 reconciliation 승인으로 사용하지 않는다.

잔고/미체결 두 조회가 정상 빈 결과여도 주문·체결 이력 근거는 없다.
`missing_sections`는 orders/fills를 남기며 `can_reconcile`은 현재 항상 false다.
실제 broker 식별·체결 중복키·수량 mapping이 없는 상태에서 이 속성을 true로 바꾸지 않는다.
새 별칭은 비밀 계좌번호가 아니라 운영자가 정한 ASCII 이름이다. 별칭 지정만으로
모의 앱이 해당 계좌에 연결됐다는 사실을 증명하지 않는다.

로컬 신규 11검사 포함 REST/WS **113 passed**, production6파일 타입0,
신규 파일 Ruff/format, 기존 보드23 통과. 전체 Windows 검사는 원격 CI에서 확인한다.

## 다음 구현과 실증

1. 공식 규격에서 읽기 전용 주문·체결 이력 API와 페이지 헤더/입력·출력 목록을 확정한다.
   후보 kt00007/ka10076는 이 작업에서 실제 어댑터 허용 목록에 추가하지 않았다.
2. 조회 범위를 영업일·계좌·환경·앱과 묶고 필요한 보존 범위를 기록한다.
3. 실제 모의 계좌 읽기와 장중 REAL 결과로 R02/R03 규격을 확인한다.
4. Q01/Q02/Q08 식별 근거를 확인하고 동일 체결 중복/역순 사례를 재생한다.
5. 위 근거가 있을 때만 REST 전용 scope와 이벤트 변환을 구현한다.
   기존 virtual scope/원장/대조 기록을 변환하거나 기존 운영 DB를 자동 인계하지 않는다.

실제 API 출력이 없으므로 주문번호·체결번호 유일성, 누적/단위 체결수량, 취소수량,
매도가능량·예약 반영을 추정하지 않았다. R04는 부분 구현이며 R05 주문은 미연결이다.

## 이력 TR 식별 기록 — 2026-10-14, `feature/rest-r04-history-spec`

공식 REST API 가이드 국내주식 계좌 TR 목록에서 이력 3건의 식별자를 확정했다.
`kt00007` 계좌별주문체결내역상세요청(orders),
`kt00009` 계좌별주문체결현황요청(orders),
`ka10076` 체결요청(fills). 모두 `POST /api/dostk/acnt`다.
기록 위치는 `adapters/kiwoom_rest_history_spec.py`이며 전송 허용 목록이 아니다.
`RestQuery` 허용 집합과 겹치지 않음을 검사하고, 해당 ID의 `capture_query`
호출은 전송 전에 `QUERY_NOT_READ_ONLY`로 차단됨을 확인했다.
필수 입력·출력 행·페이지 헤더·Q01/Q02/Q08 식별 의미는 여전히 미확정이므로
`inputs_confirmed/outputs_confirmed`는 false를 유지하고 `can_reconcile`도
false다. 실측 없이는 R05 주문·원장 연결로 진행하지 않는다.

## 이력 3건 입출력 확정 — 2026-10-14, `feature/rest-r04-history-reads`

공식 가이드 TR 목록과 계좌 예제 3건을 대조해 필수·선택 입력과 행 테이블 키를
확정했다. 구현 코드는 복제하지 않았고 필드명만 참고했다.

- `ka10076` 체결요청: 필수 `qry_tp/sell_tp/stex_tp`, 선택 `stk_cd/ord_no`,
  행 `cntr`. 식별 후보 열 `ord_no/orig_ord_no/ord_tm/cntr_pric/cntr_qty/oso_qty`.
  체결번호 열이 없다.
- `kt00007` 내역상세: 필수 `qry_tp/stk_bond_tp/sell_tp/dmst_stex_tp`,
  선택 `ord_dt/stk_cd/fr_ord_no`, 행 `acnt_ord_cntr_prps_dtl`.
  식별 후보 열 `ord_no/ori_ord/ord_tm/cntr_qty/ord_remnq/mdfy_cncl`. 체결번호 열이 없다.
- `kt00009` 체결현황: 필수 `stk_bond_tp/mrkt_tp/sell_tp/qry_tp/dmst_stex_tp`,
  선택 `ord_dt/stk_cd/fr_ord_no`, 행 `acnt_ord_cntr_prst_array`.
  식별 후보 열 `ord_no/orig_ord_no/cntr_no/cntr_tm/cntr_qty`. 체결번호는 여기만 있다.
- 페이지 방식은 기존과 같다. `cont-yn/next-key` 헤더·10페이지 상한·자동 재시도 없음.

위 열 이름은 규격 관찰이며 매핑 확정이 아니다. Q01 주문번호 유일 범위,
Q02 체결번호 유일성과 누적·단위 의미, Q08 접수 전 체결 연결은 모의계좌 실측
전까지 미확인으로 유지한다. `RestQuery`에 3건을 읽기 전용으로 추가했고
`probe_kiwoom_rest --include-history`로 5건 조회 실측이 가능하다.
기본 프로브 2건 동작은 그대로다. 5건 배치가 모여도 `can_reconcile`은 false이며
사유는 `BROKER_IDENTITY_MAPPING_UNVERIFIED`다.

## REST scope 설계 — 2026-10-14, `feature/rest-r04-scope-gates`

`execution.models.Scope`의 virtual-only 제한을 풀지 않았다. 대신
`adapters/kiwoom_rest_scope.py`에 활성화 전제조건을 코드로 고정했다.
`RestScopeProposal`은 PAPER 별칭 범위에 Q01/Q02/Q08·실측 4개 게이트와
별도 운용자 승인을 요구한다. 기본값은 전부 미확인이며 변환 함수가 없어
소프트웨어 스스로 실행 스코프를 만들 수 없다. 5건 조회 완전성과 별개로
게이트가 비어 있으면 첫 미충족 사유를 노출한다.

## 모의계좌 실측 — 2026-10-14, 사용자 PC 실행

사용자가 지정 PC에서 모의 전용 키로 직접 실행했다. 명령과 성공 기준은
`REST-R02-AUTH-READONLY.md`를 따른다.

```powershell
py -3.10-32 -m tools.probe_kiwoom_rest --execute-read-only --max-pages 3 --include-history
```

결과 3회 모두 exit 0, 5건(`kt00018/ka10075/kt00007/kt00009/ka10076`) 전부
`complete:true`, `reason:QUERY_COMPLETE_ONLY`, 각 1페이지, `observed_rows:0`.
기본 `py` 실행 1회도 동일했다. 계좌번호·원문·키·토큰은 공유받지 않았다.

확정된 사실: 모의 서버 연결, 5건 입력 승인, 행 테이블 존재, 페이지 완전성.
빈 계좌라 잔고·미체결·주문·체결 행은 0건이다. 따라서 Q01 주문번호 유일 범위,
Q02 체결번호 의미, Q08 접수 전 연결은 여전히 미확인이다. 빈 결과로는 식별
의미를 증명할 수 없으므로 게이트 3건은 false를 유지한다.
