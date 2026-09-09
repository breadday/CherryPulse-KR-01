# Agent handoff pipeline

이 디렉터리는 ChatGPT가 설계한 작업을 OpenCode 에이전트들이 순서대로 넘겨받는 공간이다.

## 역할

1. **analyzer**: 저장소를 조사하고 `TASK-ID-SPEC.md`를 작성한다.
2. **implementer**: SPEC만 계약으로 보고 코드를 수정하고 `TASK-ID-IMPLEMENTATION.md`를 작성한다.
3. **tester**: 코드를 수정하지 않고 테스트 증거를 `TASK-ID-TEST.md`에 기록한다.
4. **reviewer**: 전체 diff와 테스트를 독립 검토하고 `TASK-ID-REVIEW.md`에 PASS/CHANGES_REQUESTED/BLOCKED를 기록한다.

## 실행

PowerShell에서 자동화 브랜치 위에서:

```powershell
.scriptsun-task.ps1 `
  -TaskId TASK-001 `
  -Goal "손절을 전략·뉴스·일봉 캐시·시간 제한에서 분리하고 실패 경로 테스트를 추가"
```

검토가 끝난 뒤에만 브랜치 push와 PR 생성까지 자동화하려면:

```powershell
.scriptsun-task.ps1 `
  -TaskId TASK-001 `
  -Goal "..." `
  -AutoPublish `
  -CreatePullRequest
```

첫 실행은 `-AutoPublish` 없이 smoke test를 권장한다. `main` 직접 실행, `.env`, 브로커 전송 파일, live trading 활성화는 안전검사에서 차단한다.

## Herdr 사용

Herdr는 작업 세션과 pane을 관리한다. 공식 문서에 맞게 Herdr workspace/pane 안에서 위 runner를 실행하면 된다.

```powershell
herdr --version
herdr workspace create --cwd C:\path\to\CherryPulse-KR-01 --label CherryPulse
# 생성된 Herdr pane에서:
.\scripts\run-task.ps1 -TaskId TASK-001 -Goal "..."
```

저장소에는 확인되지 않은 `herdr.yaml` 문법을 넣지 않았다. 먼저 위 runner를 안정화한 뒤, 설치된 Herdr 버전의 `herdr --help`와 실제 pane 출력에 맞춰 native pane orchestration을 추가한다.

## 산출물 규칙

- `*-SPEC.md`: 설계 계약
- `*-IMPLEMENTATION.md`: 변경 파일과 구현 결과
- `*-TEST.md`: 실제 실행 명령과 결과
- `*-REVIEW.md`: 독립 검토 판정
- `*.log`: 각 단계의 OpenCode 원본 로그

handoff 파일과 로그에는 비밀키, 토큰, 계좌번호를 기록하지 않는다.
