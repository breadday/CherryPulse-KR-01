# TASK-005 테스트 보고서

## 결과

- 상태: **FAIL**
- 실행일: 2026-09-10
- 실계좌, 키움 COM, 실주문, `main_live.py` live 실행은 수행하지 않음.

## 실행한 명령

```powershell
python -m pytest -q tests/test_risk_sell_state_machine.py tests/test_risk_event_recovery.py tests/test_engine_risk_priority.py tests/test_risk_guard.py
```

결과:

```text
.F.F....                                                                 [100%]
2 failed, 6 passed in 1.14s
```

## 첫 번째 actionable failure

```text
FAILED tests/test_risk_sell_state_machine.py::test_cancel_request_waits_for_broker_disappearance
tests/test_risk_sell_state_machine.py:61
assert len(broker.cancels) == 1
E assert 0 == 1
```

테스트가 timeout 후 cancel 호출 1회를 기대하지만, 현재 구현에서는 cancel 기록이 0건이다. 구현 보고서에 기재된 것처럼 fake broker가 pending 조회에서 broker 주문번호를 제공하지 않는 기존 fixture와 TASK-005의 broker-ID 미확정 fail-closed 정책이 충돌하는 것으로 보인다.

두 번째 실패도 동일 테스트 파일에서 발생했다.

```text
FAILED tests/test_risk_sell_state_machine.py::test_pending_risk_order_is_reconciled_without_resubmit
tests/test_risk_sell_state_machine.py:98
E IndexError: list index out of range
```

해당 fixture가 local ID를 broker `order_no`로 사용하므로 risk event가 열린 상태로 복구되지 않는다.

## 중단 및 미실행 항목

첫 번째 관련 테스트 실패가 확인되어 지시사항에 따라 여기서 중단했다. 따라서 아래 명령은 실행하지 않았다.

- `python -m pytest -q` 전체 테스트 suite
- Python 3.8 compile check
- `git diff --check`

## 커버리지 공백

현재 저장소에는 명세가 요구한 다음 신규 테스트 파일이 없다.

- `tests/test_risk_restart_reconcile.py`
- `tests/test_risk_late_session.py`

따라서 재시작 reconciliation matrix, fake-clock 기반 14:40/15:20/15:35 경계, 독립적인 shutdown sync 및 bounded timeout은 검증되지 않았다. 구현 보고서에 언급된 partial-fill/restart matrix와 bounded-timeout 커버리지도 아직 확인할 수 없다.
