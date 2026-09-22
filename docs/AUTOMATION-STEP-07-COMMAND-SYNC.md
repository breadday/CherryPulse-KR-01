# STEP 07 — 명령 동기화 경계

| 항목 | 값 |
|---|---|
| 검증일 | 2026-09-22 |
| 작업 브랜치 | `feat/automated-rebuild-20260921` |
| 실행 범위 | 로컬 명령 envelope, 적용 버전 검사, 만료·중복·충돌 명령 처리 |
| 안전 경계 | 클라우드·인증·실계좌·실브로커·운영 배포 부작용 없음 |

이번 단계는 REBUILD-07의 외부 클라우드 연결 전에 명령 경계를 고정한다. 네트워크 transport나 인증 공급자를 임의로 구현하지 않고, 로컬에서 동일 명령의 중복·역순·만료·버전 충돌을 검증한다.

## 구현 범위

- `CommandEnvelope`가 printable ID, 계좌 ID, 기대 버전, 다음 버전, timezone-aware 만료 시각을 검증한다.
- `CommandInbox`가 현재 적용 버전과 기대 버전을 비교하고 수락 시 다음 버전으로 원자적으로 전진한다.
- 만료 명령을 `COMMAND_EXPIRED`로 거절한다.
- 동일 내용의 command ID 재수신을 `DUPLICATE`로 처리한다.
- 같은 command ID의 다른 내용 재사용을 `COMMAND_ID_CONFLICT`로 거절한다.
- 오래된 기대 버전 명령을 `STALE_COMMAND_VERSION`으로 거절한다.
- 동시 재수신은 lock으로 직렬화하여 하나만 수락한다.
- 이미 수락된 명령의 만료 후 재전송도 `DUPLICATE`로 분류하여 idempotency를 유지한다.
- 수락 명령을 로컬 history에 보존하고 외부 전송은 수행하지 않는다.

## 제외 범위

- 로그인·권한·서명·토큰 검증을 구현하지 않는다.
- Vercel, 관리형 DB, WebSocket, HTTP polling을 연결하지 않는다.
- 명령을 Windows 엔진·키움·paper broker로 전달하지 않는다.
- 실계좌 주문, 모의계좌 주문, 배포, 계좌 상태 변경을 수행하지 않는다.

## 변경 파일

- `sync/commands.py`: 로컬 명령 envelope와 inbox를 제공한다.
- `tests/test_sync_commands.py`: 수락·중복·만료·버전 충돌·ID 충돌을 검증한다.
- `docs/AUTOMATION-DEVELOPMENT-PLAN.md`: STEP 07 상태를 갱신한다.

## RED → GREEN 근거

### RED

신규 `sync.commands` 모듈이 없을 때 테스트 수집 단계에서 `ModuleNotFoundError: No module named 'sync'`로 실패했다. 이후 원자성·버전 전진·malformed 입력·clock timezone·만료 후 중복 재전송 결함에 대해 회귀 테스트를 추가했다.

### GREEN

로컬 명령 경계를 추가한 뒤 최종 특정 테스트 9개와 전체 Python 회귀 152개가 통과했다. 명령 수락은 history에만 기록되며 외부 부작용은 없다.

## 자동검사 결과

```text
PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q tests/test_sync_commands.py
9 passed in 0.18s

PYTHONPATH=.tools/python-packages:. python3 .tools/run_pytest_linux.py -q
152 passed in 2.94s

python3 -m py_compile sync/commands.py tests/test_sync_commands.py
passed
```

## 보안·운영 경계

- 이 단계의 inbox는 로컬 메모리 검증기이며 인증된 클라우드 명령 수신기가 아니다.
- 명령 수락과 실제 실행을 분리한다. 수락 history가 주문·설정 적용을 의미하지 않는다.
- 사용자 인증과 명령 서명은 실제 연결 설계에서 공식 provider·운영 환경을 확인한 뒤 별도 승인한다.
- 실계좌 및 외부 API 호출은 수행하지 않는다.

## 독립 검토

staged diff와 Python 자동검사 결과를 기준으로 독립 reviewer를 수행한다. 결함이 발견되면 RED 회귀 테스트를 먼저 추가하고 수정 후 재검토한다.

## 완료 조건

- 특정 테스트와 Python 전체 회귀가 통과한다.
- 문법 검사와 staged diff 검사가 통과한다.
- 독립 reviewer가 `passed: true`를 반환한다.
- 문서와 구현이 일치한다.
- 단계 커밋과 원격 SHA를 읽어 검증한다.
