# Multi-Agent Model Policy

## 목적

이 문서는 CherryPulse 작업에서 OpenCode 에이전트의 역할, 모델 선택,
편집 권한, 작업 인계 규칙을 정의한다. 모델을 변경해도 작업 안전성과
검증 순서는 변경하지 않는다.

## 역할과 모델

| 역할 | OpenCode agent | 기본 모델 | 책임 |
|---|---|---|---|
| Orchestrator | ChatGPT 또는 상위 세션 | GPT-5.6 Sol/Luna | 목표 정의, TASK 분할, 결과 취합, 다음 지시 |
| Analyzer | `analyzer` | GPT-5.6 Luna | 저장소 조사와 `TASK-ID-SPEC.md` 작성. Production code 수정 금지 |
| Implementer | `implementer` | DeepSeek V4 Flash 또는 GPT-5.6 Luna | SPEC 범위 내 최소 코드 수정과 구현 보고서 작성 |
| Tester | `tester` | GLM-5.3 Flash | 코드를 수정하지 않고 focused/full test 실행 및 증거 작성 |
| Reviewer | `reviewer` | GPT-5.6 Sol 또는 DeepSeek V4 Pro | 독립적인 안전성·범위·회귀 검토와 최종 판정 |

## 비용 정책

1. 단순 탐색과 반복 실행은 Zen 무료 모델을 우선 사용한다.
2. Analyzer와 Reviewer처럼 판단 오류 비용이 큰 단계는 GPT-5.6 Luna/Sol을 사용한다.
3. Implementer와 Tester는 저가 Flash 모델을 우선 사용하되, 실패하면 Luna로 재시도한다.
4. 같은 작업의 모델을 중간에 바꿀 때는 기존 handoff 파일과 baseline을 보존한다.
5. 모델 변경은 실행 시 환경변수로 우선 적용한다.

```powershell
$env:OPENCODE_MODEL="opencode/gpt-5.6-luna"
```

OpenCode 설정 파일을 변경한 경우에는 OpenCode를 재시작해야 한다.

## 실행 순서

기본 실행기는 `scripts/run-task.ps1`이며 순서는 고정한다.

1. baseline 및 safety-check
2. `analyzer`
3. `implementer`
4. `tester`
5. scope manifest 재생성
6. safety-check
7. `reviewer`
8. Reviewer가 `PASS`일 때만 publish 고려

권장 실행 예:

```powershell
$env:OPENCODE_MODEL="opencode/gpt-5.6-luna"
.\scripts\run-task.ps1 `
  -TaskId TASK-025 `
  -Goal "main_live.py에 external universe 연결 (기본 비활성)"
```

처음에는 `-AutoPublish`와 `-CreatePullRequest`를 사용하지 않는다.

## 파일 권한 계약

### Analyzer

- 읽기: 저장소 지침과 필요한 소스
- 쓰기: `docs/agent-handoff/TASK-ID-SPEC.md`만
- 금지: Production code, broker transport, `.env`, 주문 경로

### Implementer

- 읽기: SPEC, 관련 소스와 테스트
- 쓰기: SPEC의 `reviewPaths`에 명시된 파일만
- 필수: `TASK-ID-IMPLEMENTATION.md` 작성
- 금지: broker transport, secrets, live trading 활성화, 범위 밖 파일 수정

현재 TASK가 `config_live.py`를 수정해야 하면 Implementer 권한에 다음 항목이
반드시 있어야 한다.

```yaml
edit:
  "config_live.py": allow
```

### Tester

- Production code 수정 금지
- 관련 focused test를 먼저 실행하고 full suite를 실행
- 필수: `TASK-ID-TEST.md`에 실제 명령과 결과 기록

### Reviewer

- `SCOPE-MANIFEST.md`의 `reviewPaths`만 현재 TASK 변경으로 검토
- untracked source/test도 직접 읽음
- Production code 수정 금지
- 판정은 `PASS`, `CHANGES_REQUESTED`, `BLOCKED` 중 정확히 하나
- 필수: `TASK-ID-REVIEW.md` 작성

## 안전 규칙

- `RUN_MODE=live`는 모의투자 계좌라도 실제 주문 API 경로를 호출할 수 있다.
- 테스트와 리뷰에서는 Kiwoom 로그인, 주문, 취소, 실시간 COM 연결을 실행하지 않는다.
- 조건검색과 틱 단타를 임의로 활성화하지 않는다.
- external universe는 기본 비활성이고, 실패 시 fail-closed로 처리한다.
- 보유종목과 미체결 종목 감시는 후보 source와 독립적으로 유지한다.
- timeout 없는 API 대기를 추가하지 않는다.
- `.env`, 계좌번호, 토큰, 비밀번호를 handoff 문서와 로그에 기록하지 않는다.

## Handoff 산출물

각 TASK는 다음 파일을 사용한다.

- `TASK-ID-SPEC.md`: 설계 계약
- `TASK-ID-IMPLEMENTATION.md`: 구현 결과
- `TASK-ID-TEST.md`: 테스트 증거
- `TASK-ID-REVIEW.md`: 독립 리뷰 판정
- `TASK-ID-SCOPE-MANIFEST.md`: 현재 TASK의 검토 경로
- `TASK-ID-BASELINE.json`: 실행 시작 상태

## 재시도 규칙

- Stage가 timeout되면 생성된 handoff 파일과 working tree를 먼저 확인한다.
- 이미 SPEC이 있으면 Analyzer를 다시 실행하지 않고 다음 Stage부터 재개한다.
- 부분 구현 후 테스트가 실패하면 Implementer에게 실패 로그와 허용 범위를 함께 전달한다.
- baseline metadata가 있으면 같은 TASK runner를 처음부터 다시 실행하지 않는다.
- 이전 TASK 변경을 되돌리거나 덮어쓰지 않는다.
