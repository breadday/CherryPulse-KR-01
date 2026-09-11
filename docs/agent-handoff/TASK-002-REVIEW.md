# TASK-002 Review

BLOCKED

## Evidence

- TASK-002의 직접 변경(`core/risk_manager.py`, `engine.py`)은 `typing.Tuple/List/Dict`를 사용해 Python 3.8 builtin generic import 오류를 제거했으며, 보고된 Python 3.8.10 import·문법 검사와 전체 pytest 4건은 통과했다.
- 다만 main 대비 전체 변경에는 TASK-001의 RiskGuard/SQLite/engine 운영 변경도 포함되어 있다. `_check_risk_guard`가 외부 점수·일봉·전략·일반 청산 게이트보다 먼저 실행되고 `_submit_risk_sell`가 일반 매도 시간 게이트를 우회하는 점은 확인되지만, 이를 입증하는 테스트는 정상 priority 1건뿐이다.
- 손절 주문은 일반 `_check_stale_sell_order` 경로에서 식별되지 않는다(`engine.py:2709-2759`). 따라서 timeout 취소 후 `_retry_sell_after_cancel`가 일반 `_auto_sell_allowed_now`를 호출한다(`engine.py:2806-2833`). 재시도 시각 게이트/일반 정책에 의해 손절 회복이 막힐 수 있어 손절의 timeout·cancel·retry 안전 불변조건을 충족했다고 볼 수 없다.
- 재접속 및 stale-data 감시는 `main_live.py`에서 `RECONNECT_DISABLE_AFTER_HHMM` 이후 복구를 막고, `STALE_REALDATA_DISABLE_AFTER_HHMM` 이후 stale 복구 검사를 건너뛴다(`main_live.py:631-662`, `1031-1072`). 장마감 윈도우까지 보유 포지션 감시가 살아 있는지, 틱 부재 시 관찰/수동개입 상태가 유지되는지 검증한 테스트가 없다.
- `_restore_risk_events`는 보유 수량이 0이면 이벤트를 닫고 local order id를 매핑하는 읽기/로그 단계에 그친다(`engine.py:1840-1858`). broker 미체결 상태 대조, risk 전용 제한 재시도, 거부/예외 후 수동개입 전이의 엔진 수준 검증이 없다.
- 실패 경로 테스트는 RiskGuard 입력값과 SQLite 상태 저장만 다룬다. 손절 주문 거부/예외, 부분체결 후 재처리, 저장소 실패, stale/reconnect 및 재시작 복구를 증명하지 않는다. 보고서의 `4 passed`는 이 누락을 해소하지 못한다.
- 브로커 transport, live 실행, secret/account 변경은 확인되지 않았다. 그러나 위 운영 안전성 미검증 및 일반 재시도 경로의 차단 가능성 때문에 전체 diff를 승인할 수 없다.
