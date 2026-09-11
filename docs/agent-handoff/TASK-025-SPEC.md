# TASK-025 SPEC

## Goal

`main_live.py`가 TASK-024에서 준비한 외부 후보 universe를 실행 시작 흐름에 연결한다. 기본값은 반드시 비활성(`False`)로 유지하고, 명시적으로 활성화한 경우에만 외부 후보 파일을 읽어 전략별 실시간 감시 universe에 추가한다.

## Current behavior and evidence

- `main_live.py:88-95`는 `UniverseManager`를 snapshot 경로와 전략 universe 설정만으로 생성한다. `external_candidate_path`는 전달되지 않으므로 현재 live 시작 흐름은 외부 후보를 읽지 않는다.
- `main_live.py:450-524`의 `load_snapshot_and_subscribe()`는 snapshot만 로드·최신성 검증·실시간 등록·SQLite snapshot 기록 대상으로 삼는다. snapshot 파일이 없거나 오래되면 함수가 조기 반환하므로 외부 후보를 이 함수 내부에 단순히 덧붙이면 외부 로드가 snapshot 상태에 종속될 위험이 있다.
- `main_live.py:399-409`의 `_refresh_real_registration()`은 `universe.all_watch_codes()`를 사용하므로, 외부 후보가 `UniverseManager`에 정상 반영되면 기존 보유종목·미체결 종목과 함께 실시간 등록될 수 있다.
- `main_live.py:419-441`의 `_store_strategy_universe_snapshot()`은 현재 `("snapshot", "condition")`만 기록한다. external source도 전략명/selector/universe별 성과 분석에서 식별 가능하도록 별도 `source_type="external"` 행을 기록해야 한다.
- `main_live.py:1156-1158`은 snapshot 로드 후 조건검색을 시작한다. external 로드는 계좌 동기화 이후, 조건검색 시작 이전에 수행되어야 한다.
- `config_live.py:352-373`의 `STRATEGY_UNIVERSE_CONFIG`에는 전략별 snapshot/condition 사용 여부가 있고, `config_live.py:378`의 `ENABLE_CONDITION_SEARCH` 기본값은 `False`다. 외부 universe도 같은 운영 원칙에 따라 독립적인 명시적 opt-in 설정이 필요하다.
- `universe_manager.py:17-33`은 선택적인 `external_candidate_path`를 지원하고, `load_external_candidates()`는 provider/검증 오류가 나면 external source만 비운다(`:209-222`). TASK-024 테스트는 snapshot·condition·보유종목·미체결 라우팅 보존을 이미 검증한다.
- `selectors.external_candidate_provider.ExternalCandidateProvider`는 schema version 1, 필수 필드, 6자리 종목코드, timezone 포함 만료시각, 한국 시장 날짜, 만료 경계를 검증한다. main은 이 검증을 우회하거나 JSON을 직접 해석해서는 안 된다.
- 현재 working tree에는 baseline 이전 변경이 많고 `TASK-025-SCOPE-MANIFEST.md`가 baseline 경로를 제외하고 있다. 구현자는 baseline 변경을 되돌리거나 재정리하지 말고 이 명세의 current-task 경로만 수정해야 한다.

## Scope

### Files and symbols to change

1. **`config_live.py`**
   - 외부 universe opt-in 플래그를 추가한다.
     - 이름: `ENABLE_EXTERNAL_UNIVERSE`
     - 기본값: `False`
     - 환경변수 `ENABLE_EXTERNAL_UNIVERSE`를 지원하는 경우 문자열은 명시적으로 `1/true/yes/on`만 true로 해석하고, 그 외 값과 미설정은 false로 처리한다. 잘못된 값 때문에 자동 활성화되어서는 안 된다.
   - 외부 후보 파일 설정을 추가한다.
     - 이름: `EXTERNAL_CANDIDATE_FILE`
     - 기본값: `external_candidates.json`
     - 상대 경로는 `main_live.py`가 있는 프로젝트 루트 기준으로 해석한다. 비밀값이나 계좌정보를 설정에 넣지 않는다.
   - 기존 `RUN_MODE`, `ENABLE_CONDITION_SEARCH`, `STRATEGY_UNIVERSE_CONFIG`, 주문·리스크 설정의 기본값과 의미는 변경하지 않는다.

2. **`main_live.py`**
   - `MainLiveApp.__init__`에서 `ENABLE_EXTERNAL_UNIVERSE`가 true일 때만 `EXTERNAL_CANDIDATE_FILE`을 프로젝트 루트 기준 `Path`로 만들어 `UniverseManager(..., external_candidate_path=...)`에 전달한다. false일 때는 `external_candidate_path=None`을 전달하여 provider를 만들지 않는다.
   - 외부 후보 로드 전용 메서드를 추가한다(권장 심볼: `load_external_candidates_and_subscribe`). 이 메서드는 다음 계약을 지킨다.
     1. 플래그가 false이면 파일 존재 여부, JSON 내용, provider를 확인하지 않고 external source를 비활성 상태로 유지한 뒤 반환한다.
     2. 플래그가 true이면 `self.universe.load_external_candidates()`만 사용한다. 현재 시각을 직접 전달한다면 provider 계약에 맞는 timezone-aware 시각이어야 하며, naive datetime을 전달하지 않는다.
     3. 성공 시 후보 수와 전략별 external count를 로그로 남기고 `_refresh_real_registration()`, `_store_strategy_universe_snapshot()`, `_log_strategy_universe_summary()`를 호출한다.
     4. 파일 없음, invalid JSON/schema/field, 만료 전부 제외, unknown `strategy_tag` 등 모든 `ExternalCandidateError`를 안전하게 처리한다. 사용자에게 예외를 전파해 broker/account startup을 중단시키지 말고, `UniverseManager`가 비운 external source를 유지한 채 오류 로그와 throttled Telegram 알림(기존 패턴)을 남긴다.
     5. 외부 로드 실패가 snapshot 로드 성공/실패, 조건검색 시작, 계좌 동기화, 보유종목 및 열린 주문 감시를 막지 않도록 한다.
   - `_store_strategy_universe_snapshot()`의 source 반복에 `external`을 추가한다. source별 rows는 `strategy_source_codes(strategy_name, source_type)`에서 가져오고, 기존 snapshot/condition 행을 external과 합치지 않는다.
   - `_log_strategy_universe_summary()`에 external count를 추가하되 기존 로그 필드와 의미는 유지한다.
   - `boot()`의 startup 순서를 계좌/미체결 동기화와 기존 snapshot 처리 후, 조건검색 시작 전에 외부 로드 메서드를 호출하도록 연결한다. 단, snapshot 메서드의 early return 때문에 external 로드가 생략되지 않아야 한다.
   - run-mode/startup 로그에 external universe의 enabled/disabled 상태와 파일명(활성 시)을 표시한다. 파일 내용, 토큰, 계좌번호는 로그/알림에 출력하지 않는다.

3. **`tests/test_task025_external_universe.py`** (신규)
   - 실제 `QApplication`, Kiwoom COM, broker login/order, network, SQLite를 호출하지 않는 단위 테스트를 추가한다. `MainLiveApp`은 필요한 속성만 구성하거나 monkeypatch/fake object로 검증한다.
   - TASK-024의 provider/universe 계약을 중복 구현하지 말고 main의 wiring, opt-in, failure isolation, refresh/store 호출을 검증한다.

## Invariants and safety constraints

- 외부 universe는 기본 비활성이다. 기본 설정에서 외부 파일이 존재해도 신규 진입 후보나 실시간 등록에 절대 영향을 주지 않는다.
- 활성화해도 external 후보는 provider와 `UniverseManager`의 schema/date/expiry/strategy-tag 검증을 통과한 후보만 사용한다. main에서 검증을 완화하거나 fallback symbol을 삽입하지 않는다.
- 외부 source는 snapshot·condition source와 독립적이다. 외부 실패/만료/누락은 external만 empty로 만들고 snapshot·condition membership은 유지한다.
- 이미 보유한 종목과 미체결 주문은 candidate source와 무관하게 기존 `_all_watch_codes()` 및 `UniverseManager.should_route()` 경로로 계속 감시한다.
- 전략 태그는 해당 전략 universe에만 들어간다. 외부 후보를 모든 전략에 broadcast하지 않으며, TASK-024의 `UniverseManager.replace_external_candidates()`가 정의한 exact `strategy_tag` 매핑을 그대로 사용한다.
- external source 기록은 `source_type="external"`로 분리한다. 전략명과 `universe_name`을 기존 규칙(`{strategy_name}_universe`)에 맞춘다.
- external 로드 실패는 신규매수 후보를 추가하지 않는 fail-closed 동작이어야 하며, 실패한 이전 external 후보를 남겨 stale 후보가 재사용되게 해서는 안 된다(TASK-024 계약).
- API/COM 호출에 새 무기한 대기를 만들지 않는다. 이 task는 외부 파일 로컬 읽기만 추가하며 broker transport를 변경하지 않는다.
- `RUN_MODE=live`에서는 활성화된 외부 후보가 실제 주문 경로로 이어질 수 있다. 기본값을 바꾸지 말고, 테스트에서 live order를 호출하거나 안전장치를 해제하지 않는다.
- `main_live.py`의 기존 장 종료 즉시 종료, 계좌 동기화, 조건검색 비활성 기본값, shutdown/reconnect 흐름은 보존한다.
- 수정 범위는 `config_live.py`, `main_live.py`, `tests/test_task025_external_universe.py`, 이 SPEC에 한정한다. `engine.py`, broker, strategies, `universe_manager.py`, provider 및 `.env`는 수정하지 않는다.

## Acceptance tests

### Focused tests

Run with Python 3.10+:

```powershell
python -m pytest -q tests/test_task025_external_universe.py tests/test_task024_external_universe.py tests/test_task023_external_candidate_provider.py tests/test_task017_universe_isolation.py
```

Required cases:

1. **Default disabled**: config default is false; a present valid external file is not read, provider path is not configured, no external symbols appear in `all_watch_codes()` or strategy membership, and no external refresh/store call is made by startup wiring.
2. **Opt-in success**: with the flag true and a valid schema-1 file, candidates are loaded once during boot after snapshot handling and before condition-search startup; only matching strategy tags receive them; real registration contains the merged candidate set.
3. **Snapshot independence**: external candidates load even when snapshot is absent/empty or snapshot freshness fails; conversely an external failure does not prevent a valid snapshot from remaining registered.
4. **Missing file**: enabled mode logs/alerts the error, leaves external empty, does not abort boot, and still preserves valid snapshot plus held/open-order watch codes.
5. **Malformed/schema/unknown strategy**: enabled mode handles each `ExternalCandidateError`, clears previously loaded external symbols via `UniverseManager`, preserves snapshot/condition sources, and does not submit an order.
6. **Expired/boundary candidates**: `expires_at == as_of` and all-expired files produce no external new-entry candidates; no stale prior external candidate remains after reload.
7. **Persistence/observability**: successful external source rows are passed to SQLite storage with `source_type="external"`, while snapshot and condition calls remain separate. If the test fake has no SQLite, assert calls without invoking a real database.
8. **Routing regression**: external failure or disabled mode does not change routing for a held symbol or a symbol with an open order; unrelated symbols remain unrouted.
9. **Startup ordering**: use fakes/call recording to prove account/pending synchronization and snapshot handling occur before external load, and external load occurs before `maybe_start_condition_search()`; no broker login or order API is invoked by the test.

### Static/regression validation

```powershell
.venv\Scripts\python.exe -B -c "from pathlib import Path; [compile(Path(p).read_text(encoding='utf-8-sig'), p, 'exec') for p in ['main_live.py','config_live.py','universe_manager.py','selectors/external_candidate_provider.py']]; print('syntax ok')"
python -m pytest -q
git diff --check
```

The full suite must retain all prior TASK-023/TASK-024/TASK-017 results. Do not claim live startup, Kiwoom connection, account synchronization, or real-order behavior was tested unless it was explicitly and safely run; unit tests must not run those paths.

## Rollback considerations

- If wiring causes startup or snapshot regressions, revert only the TASK-025 changes in `main_live.py` and `config_live.py`; `UniverseManager`/provider remain backward-compatible because their external path is optional.
- Operational rollback is immediate: leave `ENABLE_EXTERNAL_UNIVERSE=False` (or remove the environment override) and restart. Existing snapshot/condition behavior then uses the pre-TASK-025 path, while external files are ignored.
- If an enabled external file is suspect during a live/paper session, disable the flag before the next startup; do not hand-edit `condition_snapshot.json` and do not delete/alter held-position or open-order state.
- Do not roll back or overwrite baseline-unrelated working-tree changes, prior handoff artifacts, generated runtime state, secrets, or broker files.
