CHANGES_REQUESTED

Evidence:

- TASK-006 명세의 핵심 계약이 구현되지 않았다. `core/models.py`의 `Order`에는 `purpose`, `risk_event_id`, `broker_order_id` 정식 필드가 없고, `core/order_manager.py`에는 명시적 local↔broker binding, broker ID 조회, event 기준 유일 risk SELL 조회 API가 없다.
- `engine.py`가 위 메타데이터를 동적 속성으로 붙이고 `broker_to_local_id`를 직접 갱신하므로 재시작·복구·타입 계약이 명세와 다르다. `on_fill`은 명확한 formal binding 없이 `resolve_order_id`에 의존하며, 누적/동일 callback의 delta 보장도 신규 acceptance 테스트로 입증되지 않았다.
- `_check_stale_risk_order` 자체는 실행 가능한 위치에서 `order.broker_order_id`를 확인하고 timeout cancel 성공 후 `CANCEL_REQUESTED`를 유지한다. 따라서 제출된 정상 경로의 broker ID 전달 및 confirmation 전 재주문 방지는 일부 확인된다. 다만 broker ID 미확정/복수 후보, partial fill, restart mapping, confirmation timeout 이후 broker/account 조회 예외·모호성에 대한 자동 검증이 없다.
- stop-loss 호출 위치는 valid tick에서 external/news·daily/strategy 경로보다 앞서며 기존 ordinary stop-loss 블록은 제거되어 time gate, grace window, trend/news/cache shortcut에 막히지 않도록 의도되어 있다. 그러나 관련 failure-path 및 stale/reconnect가 market-close window까지 살아 있는지 검증한 테스트가 없으므로 이 안전성을 완전 승인할 증거가 부족하다.
- 테스트 보고의 8개 테스트/전체 pytest 통과는 확인 범위가 좁다. 명세가 요구한 `tests/test_risk_restart_reconcile.py`가 존재하지 않으며, partial 40/100→60 복구, duplicate cumulative fill, pending/account 예외, missing/ambiguous identity, retry 호출 0건을 자동 검증하지 않는다.
- `git diff main...HEAD`에는 TASK-006 범위를 벗어난 automation/docs/config 및 live engine 기반 변경이 다수 포함되어 있다. TASK-006 명세는 최소 변경 파일과 broker transport·main_live·무관 문서 불변을 요구하므로, 누적 diff의 소유 범위를 정리하거나 TASK-006 변경에서 분리해야 한다.

Required before approval:

1. `Order` formal fields와 `OrderManager`의 양방향·fail-closed binding/query API를 구현한다.
2. risk submit/reconcile/fill/restart 경로를 해당 API로 전환하고, identity 불명확 시 place/cancel 0건을 보장한다.
3. 명세의 restart/partial/duplicate-fill/exception/ambiguous-identity failure-path 테스트를 추가하고 전체 acceptance를 실행한다.
4. main 대비 누적 변경에서 TASK-006과 무관한 변경을 분리하고 broker/live/secret 변경이 없는지 다시 확인한다.
