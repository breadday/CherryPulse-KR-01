# TASK-025 TEST

## 실행 환경

- Python 3.8.10 32-bit
- 영웅문 API, Kiwoom COM, 네트워크, 계좌 동기화, SQLite 및 주문 API 미실행

## 집중 검증

```text
python -m pytest -q tests/test_task025_external_universe.py
..................                                                       [100%]
18 passed
```

```text
python -m pytest -q tests/test_task025_external_universe.py tests/test_task024_external_universe.py tests/test_task023_external_candidate_provider.py tests/test_task017_universe_isolation.py
..................sssss.................ssss                             [100%]
35 passed, 9 skipped in 0.54s
```

기존 TASK-017/024 테스트의 9건은 테스트 자체의 Python 3.10 이상 조건 때문에 Python 3.8에서 skip됐다. TASK-025 테스트 18건은 모두 실행됐다.

## 전체 회귀

```text
python -m pytest -q
103 passed, 22 skipped in 156.87s (0:02:36)
```

## 정적 검증

```text
python -B -c "from pathlib import Path; [compile(Path(p).read_text(encoding='utf-8-sig'), p, 'exec') for p in ['main_live.py','config_live.py','universe_manager.py','selectors/external_candidate_provider.py','tests/test_task025_external_universe.py']]; print('syntax ok')"
syntax ok
```

- `git diff --check -- config_live.py main_live.py tests/test_task025_external_universe.py` 통과
- CRLF 변환 예고 외 whitespace 오류 없음

## 잔여 위험

- 실제 `broker/kiwoom_broker.py`는 기존 `int | None` 타입 표기로 인해 Python 3.8 import 시 실패한다. TASK-025 테스트는 명세에 따라 브로커를 가짜 모듈로 격리했으므로 실제 영웅문 시작 성공을 검증한 것으로 간주하지 않는다.
