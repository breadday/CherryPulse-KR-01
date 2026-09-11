# PASS

Evidence:

- `tests/test_task011_recovery_isolation.py`의 12개 테스트가 통과했다.
- 전체 pytest suite가 `53 passed`로 통과했다.
- pending query exception은 event 상태를 변경하지 않고 반환하며, 새 place/cancel 경로를 호출하지 않는다.
- recovery cutoff와 heartbeat/shutdown ordering acceptance가 직접 검증됐다.
- 변경된 Python 파일 문법 검사와 `git diff --check -- engine.py`가 통과했다.
- broker transport, `.env`, live enablement, 실제 주문·체결 경로는 범위와 실행에서 제외됐다.
