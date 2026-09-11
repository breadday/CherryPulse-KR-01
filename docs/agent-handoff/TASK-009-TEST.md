# TASK-009 테스트 보고서

## 실행 환경

- 작업 디렉터리: `C:\workspace\CherryPulse-KR-01`
- 검증일: 2026-09-10
- 실제 키움/COM 연결 및 실시간 주문은 실행하지 않음

## 실행 결과

### 1. TASK-009 관련 좁은 테스트

명령:

```powershell
python -m pytest -q tests/test_risk_restart_reconcile.py tests/test_risk_sell_state_machine.py
```

결과: **PASS — 12 passed in 1.63s**

확인된 항목:

- pending binding 실패 시 local order/mapping/risk map rollback
- 식별된 risk event만 `MANUAL_INTERVENTION_REQUIRED`로 전환
- 누적 체결 및 중복 체결 idempotency
- cancel confirmation timeout fail-closed
- shutdown gate 이후 risk/auto sell, retry, cancel 호출 차단

### 2. 전체 테스트 스위트

명령:

```powershell
python -m pytest -q
```

결과: **PASS — 16 passed in 2.05s**

### 3. 문법 검사

명령:

```powershell
python -B -c "from pathlib import Path; files=['main_live.py','engine.py','core/order_manager.py']; [compile(Path(p).read_text(encoding='utf-8-sig'),p,'exec') for p in files]; print('syntax ok')"
```

결과: **PASS — `syntax ok`**

### 4. diff 검사

명령:

```powershell
git diff --check
```

결과: **FAIL/WARNING — 기존 작업 트리의 `docs/agent-handoff/TASK-001`~`TASK-008` 로그 파일들에 trailing whitespace가 다수 존재**. TASK-009 테스트 수행 중 해당 무관 파일은 수정하지 않음.

### 5. 금지 파일 확인

명령:

```powershell
git diff --name-only -- broker/kiwoom_broker.py .env
```

결과: **PASS — 출력 없음** (`broker/kiwoom_broker.py`, `.env` diff 없음)

## 경계 및 호출 결과

- 14:40: 관련 직접 경계 테스트 파일이 없어 독립 cutoff 제거를 **직접 검증하지 못함**.
- 15:20: 관련 직접 경계 테스트 파일이 없어 stale recovery eligibility를 **직접 검증하지 못함**.
- 15:35: `main_live.py` heartbeat/recovery 경계 테스트가 없어 shutdown 선행, recovery 미호출을 **직접 검증하지 못함**.
- engine shutdown gate 테스트에서는 fake broker `place_order` **0회**, `cancel_order` **0회**.
- pending binding failure 테스트에서는 fake broker `place_order` **0회**, `cancel_order` **0회**.
- risk sell binding 실패 후 broker 제출 자체(`place_order=1`, `cancel_order=0`)를 확인하는 별도 테스트는 현재 테스트 스위트에 없음.

## 신규/수정 테스트 수

- TASK-009 구현 보고서 기준 수정 테스트 파일: 2개
- 현재 TASK-009 관련 테스트 함수: 12개 실행
- TASK-009 전용 `main_live` recovery-window 테스트: 없음

## 남은 테스트 공백

명세의 다음 acceptance 경로는 현재 테스트로 고정되어 있지 않다.

1. 14:39/14:40/14:41 및 15:19/15:20/15:21/15:34 recovery 경계
2. 15:35/15:36 heartbeat ordering 및 반복 callback 경합
3. pending/account query exception의 event 격리
4. missing broker ID, duplicate/ambiguous identity, local/broker conflict의 각 경로
5. `_submit_risk_sell()` binding 실패 후 durable event 보존과 local 상태 정리

따라서 자동화 테스트 기준으로는 전체 suite가 통과했지만, TASK-009 명세의 모든 acceptance condition이 검증된 것은 아니다.

## 결론

**조건부 PASS.** 기존 16개 테스트와 문법 검사는 통과했다. 다만 `main_live.py` 시간 경계 및 일부 binding/query 오류 격리 acceptance 테스트가 없어 해당 동작은 추가 테스트가 필요하다. `git diff --check` 실패는 기존 무관 로그 파일의 trailing whitespace 때문이다.
