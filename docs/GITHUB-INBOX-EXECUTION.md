# GitHub 전달함 2단계: Codex 읽기 전용 검토

2026-11-17. 대상은 AI5이며 최초 설치와 모델 실행은 아직 AI5에서 검증해야 한다.
기존 `receiver.py`의 ping/status는 유지한다. 새 `executor.py`는 이 기능과 v2 review를
한 프로세스에서 처리하며, 같은 대상 잠금을 공유하므로 기존 감시기와 동시에 실행하지 않는다.
REST migration, 주문 설정, 기존 개발 폴더는 변경하지 않는다.

## 구현한 범위

- 소유자 breadday가 작성한 `[hermes-task]` 열린 Issue의 정형 JSON만 받는다.
- 자연어 지시는 Codex의 stdin으로 전달한다. Issue에서 경로·명령·실행 파일·CLI 옵션을 받지 않는다.
- 분석 자료는 별도 public clone의 지정 SHA에 커밋된 수신기 소스·테스트·안내 6개뿐이다.
  Git object를 `git show <SHA>:<고정경로>`로 읽는다. 미커밋 파일·.env·계좌·DB를 읽지 않는다.
- Codex는 작업마다 별도 임시 폴더에서 `read-only`, approval `never`로 실행한다.
  셸, apps, plugins, hooks, memories, multi_agent, 웹 검색을 끈다. 사용자 config는 로드하지 않는다.
  임시 폴더에는 프로젝트 소스/config/의존성을 설치하지 않는다. 자료는 프롬프트 데이터로만 전달한다.
- 기존 ChatGPT CLI 로그인을 사용하고 `forced_login_method=chatgpt`를 적용한다.
  API 키·GitHub 토큰·브로커 인증 환경변수를 자식 프로세스에 넘기지 않는다.
  수신기가 인증 파일을 직접 읽거나 복사하지 않는다. API 방식이나 알 수 없는 로그인 응답이면 중단한다.
- AI 호출은 요청당 최대 1회 시도, 시간 제한 600초, 한 주기 최대 한 요청이다.
  대기 중에는 AI를 호출하지 않는다. 실제 실행은 기존 구독 사용량을 소비하며 무제한/0원 사용을 보장하지 않는다.
  한도 초과·실패 후 자동 유료 전환이나 재호출은 하지 않는다.

이 단계는 **공개 소스의 AI 분석**이다. 코드 수정·테스트 실행·커밋·push·배포·주문이나
Hermes 직접 실행, 비공개 프로젝트 점검은 구현하지 않았다. 쓰기 가능한 자동 개발은 다음 단계다.
모델은 사용자 config의 모델 대신 Codex 기본 모델을 사용하므로 로컬 설치 검증 때 안내한다.
프로필/Gateway/모델 공급자를 자동 변경하거나 새 로그인을 시작하지 않는다.

## 요청과 결과

```json
{
  "version": 2,
  "target": "AI5",
  "action": "review",
  "project": "cherrypulse-inbox",
  "expected_head": "<설치할 정확한 40자리 커밋 SHA>",
  "instruction": "공개된 수신기 코드에서 중복 AI 실행 방지와 다음 개발 작업 하나를 검토해줘."
}
```

SHA가 로컬 HEAD와 다르면 실행하지 않는다. 브랜치 최신 코드를 자동 pull하지 않는다.
전달함 저장소가 공개이므로 지시 본문에도 계좌·비공개 프로젝트 정보·로컬 경로를 쓰지 않는다.

공개 댓글에는 `code`, `llm_called`, `orders_called=false`, 검증된 `verdict/next_step` enum과
공개 소스 근거 경로만 올린다. 모델이 쓴 자유 텍스트, stdout/stderr, 로그인 응답을 올리지 않는다.
한국어 상세 분석은 로컬 state-dir의 `review-AI5-<Issue번호>.json`에 저장한다.
공개 결과 `READY`는 모델의 소스 검토 의견이며 실제 Windows/주문/운영 인수를 뜻하지 않는다.

## 재시작 및 전송 오류

SQLite journal은 AI 호출 전에 `(target, Issue번호)`를 선점하고 task hash를 저장한다.
완료 결과도 GitHub 댓글 전송 전에 저장한다. 댓글 전송에 실패하면 다음 주기에 저장 결과만 보낸다.
실행 도중 재시작하면 `INTERRUPTED_NO_RETRY`, Issue 본문을 수정하면 `TASK_CHANGED_NO_RETRY`를 기록한다.
시간 초과나 오류도 종료 결과이며 자동 재실행하지 않는다. 필요한 재시도는 원인을 확인하고 **새 Issue**로 요청한다.
일시 오류 때문에 실행 전 선점만 된 요청도 자동 재시도하지 않는 보수적인 정책이다.
`llm_called=true`는 호출 시도/중단 여부가 불명확한 경우도 포함하며 과금 확정 표시는 아니다.

state-dir은 전용 clone 밖의 허용된 사용자 전용 위치에 보존한다. 삭제·초기화하지 않는다.
journal과 GitHub 댓글을 모두 잃으면 중복 실행 방지를 보장할 수 없다.
댓글 전송 자체는 네트워크 반영 지연으로 중복될 수 있지만 journal이 보존되면 AI는 재실행하지 않는다.
강제 종료나 SQLite 기록 실패 이후에는 프로세스와 journal 상태를 확인하며 자동으로 초기화하지 않는다.

## AI5에서 1회 업데이트·시험

1. 실제 PC `BREADDAY_AI5`, GitHub 계정 `breadday`를 확인한다. 토큰 값은 출력하지 않는다.
2. 기존 전경 receiver의 정확한 실행 경로·명령을 확인해 그 감시기만 정상 종료한다.
   관련 없는 Hermes/개발 프로세스를 종료하지 않는다. 종료가 제한되면 우회하지 않는다.
3. 기존 개발 폴더와 분리된 새 clone에 이번 실행 기능 브랜치를 받는다.
   설치 Issue에 지정된 정확한 SHA를 검증한다. 기존 clone을 reset/checkout/stash하지 않는다.
   경로는 Hermes가 쓰기를 허용하는 workspace 안에서 정하고 기존 경로는 덮어쓰지 않는다.
4. 표준 Python 3.11 이상으로 아래 단위 테스트를 실행한다. 거래 엔진 의존성 설치는 필요 없다.
5. 설치된 Codex native 실행 파일의 절대 경로를 확인한다. Windows는 `.exe`가 필요하다.
   `.cmd`/`.bat`/PowerShell 래퍼는 실행하지 않는다. `Get-Command codex -All`로 찾되
   실제 native 파일이 없으면 설치 상태만 보고한다. 임의 다운로드·업데이트하지 않는다.
6. `--check-runtime`을 실행한다. 필요한 CLI 옵션이 없거나 ChatGPT 로그인 확인이 안 되면
   멈추고 고정 오류 코드만 보고한다. Hermes 로그인과 Codex 로그인은 별개다.
   이 검사는 AI를 호출하지 않는다. 자동 로그인·인증정보 이동·API 전환을 하지 않는다.
7. dry-run에서 설치 Issue에 명시된 v2 시험 요청을 확인한다. 실제 단발 실행은
   `--enable-review`를 명시한다. 처음에는 `--watch`를 붙이지 않는다.
8. 공개 결과가 `REVIEW_COMPLETED`, `llm_called=true`, `orders_called=false`인지 확인하고
   로컬 상세 결과가 있는지 확인한다. 원문은 공개 Issue에 붙이지 않는다.
9. 단발 재실행으로 완료 댓글과 journal이 그대로이고 AI가 반복 호출되지 않는지 확인한다.
10. 성공하면 아래 새 executor의 `--watch` 프로세스 하나만 실행하고 설치 Issue에 결과를 기록한다.
    실패하면 기존 receiver를 재시작할 수 있지만 v2 검증 완료라고 보고하지 않는다.
    예약 작업·서비스·Gateway·절전 정책·부팅 자동 실행은 변경하지 않는다.

아래 변수는 AI5에서 확인한 **로컬 경로**를 넣는다. 실제 경로를 공개 댓글에 붙이지 않는다.

```powershell
Set-Location $inboxCloneRoot
python -B -m unittest discover -s tools/github_inbox -p "test_*.py" -v
$reviewArgs = @(
  '-B', 'tools/github_inbox/executor.py', '--target', 'AI5',
  '--project', $inboxCloneRoot, '--codex', $nativeCodexPath,
  '--state-dir', $privateInboxStateRoot
)
python @reviewArgs --check-runtime
python @reviewArgs --dry-run
python @reviewArgs --enable-review
python @reviewArgs --enable-review
# 위 단발 검증이 성공했을 때만 실행:
python @reviewArgs --enable-review --watch
```

창 종료·로그아웃·절전 시 멈춘다. 이전 단계와 마찬가지로 이 ChatGPT 대화도 종료 후
GitHub 결과를 계속 감시하지 않는다. 사용자가 결과 확인을 요청하면 읽어 확인한다.
기존 감시기는 자동으로 새 코드를 설치하지 않으므로 이번 업데이트는 로컬 Hermes에서 한 번 수행한다.
ZenBook은 설치 대상이 아니며 기존 REST 전환 브랜치를 수정하지 않는다.

## 검증 기록

Linux Python 3.12에서 표준 unittest **26건 통과** (기존 10건 + executor 16건).
재시작 선점, 본문 변경, 시간 초과, POST 실패 후 결과 재전송, 잘못된 사용자,
API 키 환경변수 제거, 로그인 방식, SHA 불일치, 공개 결과 제한, dry-run 무호출을 검증했다.
실제 Codex AI 호출·Windows native 실행·AI5 업데이트·왕복 검증은 미실행이다.
프로젝트 전체 pytest/Ruff/타입 검사/거래 엔진 인수 결과로 대체하지 않는다.

공식 CLI 자료 (2026-11-17 확인):
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/cli/reference
- https://learn.chatgpt.com/docs/config-file/config-reference
