# AI5 자동 개발 1건: 수정 → 검증 → 커밋 → Draft PR

2026-11-17. 전달함은 공개 저장소 `breadday/CherryPulse-KR-01`이다.
이번 개발 프로필은 `inbox-lab`이며 첫 실제 자동 개발 작업을 위한 범위다.
키움 트레이더·종목헌터·CherryPlus 운영 코드의 범용 자동 수정은 아직 지원하지 않는다.

## 실행 흐름

1. 소유자 breadday의 열린 `[hermes-task]` Issue에서 v3 `develop` 요청을 읽는다.
2. 기존 journal에 작업을 선점한다. 실제 PC는 `BREADDAY_AI5`여야 한다.
3. 고정된 공개 저장소의 `feat/github-inbox-autodev` 브랜치를 새 전용 clone에 받는다.
   HEAD가 지시의 정확한 SHA와 다르면 멈춘다. 기존 개발 clone은 사용하지 않는다.
4. 기존 ChatGPT 로그인 Codex에 공개 자료와 지시를 전달해 세 파일의 변경안을 생성한다.
   모델은 기존 v2와 같은 도구 없는 읽기 전용 모드이며 파일을 직접 수정하거나 명령을 실행하지 않는다.
5. 실행기가 경로·크기·중복·비밀키 형태·좁은 Python 문법 계약을 검사한 뒤 파일에 적용한다.
6. 실제 별도 Python 프로세스에서 생성 unittest와 고정 인수 검사를 실행한다.
7. 통과한 파일 내용과 검증 결과를 SQLite에 저장한다.
8. 실행기가 GitHub API로 커밋과 작업 전용 브랜치를 생성하고 Draft PR을 작성한다.
9. 원래 Issue에 단계·테스트 개수·커밋 SHA·PR 링크를 자동 회신한다.

## 첫 작업의 파일 범위와 계약

다음 세 경로만 변경할 수 있다. 삭제·경로 추가·운영 실행기 변경은 허용하지 않는다.

| 파일 | 내용 |
|---|---|
| `tools/github_inbox/lab/status_text.py` | `describe(code)` 순수 함수 |
| `tools/github_inbox/lab/test_status_text.py` | 표준 unittest |
| `docs/orchestration/STATUS-TEXT.md` | 한국어 사용 설명 |

함수 매핑: WAITING → 대기 중, RUNNING → 개발 중, TEST_FAILED → 검증 실패,
PR_CREATED → PR 작성 완료, UNKNOWN 및 미지정 문자열 → 확인 필요.
문자열이 아닌 값은 TypeError로 거부한다. 고정 계약 검사는 모델이 수정할 수 없는
설치된 실행기의 `autodev_acceptance.py`에서 별도로 실행한다.
이번 작업은 상태 안내용 보조 모듈의 자동 개발 시험이며 기존 감시 화면에 자동 연결하지 않는다.

모델 응답은 JSON 파일 내용뿐이며 GitHub·브로커·API 키 환경변수는 넘기지 않는다.
구현은 import 없는 순수 함수, 테스트는 unittest/status_text만 허용하는 제한된 문법을 검사한다.
이는 범용 Python/OS 샌드박스가 아니다. 테스트는 설치된 사용자 권한의 별도 프로세스로 실행되므로
수정 범위를 임의의 프로젝트나 패키지 설치·임의 명령 실행으로 확대해서 사용하지 않는다.
전체 거래 엔진 테스트나 전략 성능 검증으로 해석하지 않는다.

## 중단·재시작·오류 처리

- 모델 생성은 요청당 최대 1회 시도다. 생성/적용/테스트 중 중단되면 재시작 시
  `INTERRUPTED_NO_RETRY`로 멈춘다. 작업 clone과 상태를 남겨 확인 후 새 Issue로 요청한다.
- 테스트 실패 시 `TESTS_FAILED`, 실패 단계 `TEST`를 회신하고 작업 clone과 로컬 로그를 보존한다.
  실패 코드를 커밋·PR로 게시하거나 자동 AI 재수정을 반복하지 않는다.
- 생성된 내용이 경로/문법 계약을 벗어나면 `PATCH_REJECTED`다. 자동으로 범위를 넓히지 않는다.
- 검증 통과 후에는 파일 내용과 UTC 커밋 시각을 영속 저장한다. 외부 전송 실패는
  `PUBLISH_PENDING`이며 다음 주기에는 저장된 내용으로 게시만 재시도한다. 모델·테스트는 재실행하지 않는다.
- 커밋의 부모·내용·작성자·시각을 고정해 응답 유실 시 같은 Git object를 재생성한다.
  작업 브랜치는 `orchestration/AI5-issue-<번호>`이며 같은 SHA만 인정한다.
  다른 SHA가 있으면 `BRANCH_CONFLICT`로 멈추고 강제 갱신하지 않는다.
- 같은 head/base의 PR을 먼저 조회해 기존 PR이 있으면 재사용한다. 닫힌 PR도 다시 만들거나 열지 않는다.
- 최종 댓글 전송 실패 시 저장된 결과만 재전송한다. 완료 댓글 마커와 journal을 함께 사용한다.
  GitHub 조회 반영 지연 중 댓글 중복 가능성과 journal·댓글 동시 유실 한계는 기존과 같다.

로컬 state-dir의 `workspaces/AI5-<Issue번호>`에 clone을 보존한다.
`development-AI5-<번호>`에는 실제 테스트 로그, `handoff-AI5-<번호>.json`에는 고정된 결과를 남긴다.
공개 회신은 자유 텍스트나 stdout/stderr 대신 단계·고정 코드·검증 개수·공개 PR 링크를 사용한다.
PR diff에서 실제 변경을 확인할 수 있어 성공 결과를 별도로 복사해 전달할 필요가 없다.
실패 상세 로그·비공개 로컬 자료는 자동 공개하지 않는다.

## 요청 규격

```json
{
  "version": 3,
  "target": "AI5",
  "action": "develop",
  "project": "inbox-lab",
  "expected_head": "<설치/실행 지시의 정확한 40자리 SHA>",
  "instruction": "상태 코드 한글 안내 함수를 구현하고 unittest와 사용 설명을 작성해줘."
}
```

Issue에서 실행 파일·명령·로컬 경로·저장소·임의 테스트 명령을 받지 않는다.
프로필이 고정된 것이므로 instruction을 바꿔도 수정 파일이나 기능 계약을 확대할 수 없다.

## AI5에서 1회 업데이트

1. 설치 Issue의 정확한 SHA를 **새 별도 clone**에 받는다. 기존 설치/작업 디렉터리의
   checkout/reset/stash/pull을 하지 않는다. 허용된 workspace 내 짧은 경로를 정한다.
2. 현재 executor 프로세스의 인수에서 기존 state-dir을 확인하고 **같은 영속 state-dir**을 사용한다.
   기존 DB를 삭제·초기화하거나 인증 파일을 읽지 않는다. 로컬 경로를 공개 댓글에 올리지 않는다.
3. `python -B -m unittest discover -s tools/github_inbox -p "test_*.py" -v`를 실행한다.
   모델·브로커·GitHub API는 호출하지 않는 로컬 테스트다. 실제 Git과 테스트 프로세스는 사용한다.
4. 기존 `executor.py --check-runtime`으로 native Codex/ChatGPT 인증을 확인한다.
   새 로그인·API 키·유료 전환·자동 다운로드를 하지 않는다. 이전에 확인한 native .exe를 재사용한다.
5. 기존 전경 감시기만 정상 종료한 뒤 새 autodev.py의 dry-run을 수행한다.
   모든 버전은 같은 AI5 프로세스 잠금을 사용한다. 다른 Hermes/개발 프로세스는 종료하지 않는다.
6. 설치 Issue에 적힌 v3 시험 요청 1건을 `--enable-development` 단발 실행한다.
   실제 모델 생성은 기존 구독 사용량을 사용하고, 통과하면 공개 Draft PR을 생성한다.
7. PR의 변경이 세 허용 파일뿐인지, 생성 테스트/고정 인수 검사가 통과했는지,
   재실행 시 모델·커밋·PR이 중복되지 않는지 확인한다. 결과를 설치 Issue에 기록한다.
8. 성공하면 autodev 감시기 1개를 실행한다. v1 ping/status와 v2 review도 같은 프로세스가 처리한다.
   실패하면 상태를 보존하고 이전 읽기 전용 감시기로 복구할 수 있다.

```powershell
Set-Location $newInboxCloneRoot
python -B -m unittest discover -s tools/github_inbox -p "test_*.py" -v
$commonArgs = @('--target', 'AI5', '--project', $newInboxCloneRoot,
  '--codex', $existingNativeCodexPath, '--state-dir', $existingPrivateStateRoot)
python -B tools/github_inbox/executor.py @commonArgs --check-runtime
# 기존 감시기를 정상 종료한 후:
python -B tools/github_inbox/autodev.py @commonArgs --dry-run
python -B tools/github_inbox/autodev.py @commonArgs --enable-development
python -B tools/github_inbox/autodev.py @commonArgs --enable-development
# 단발 검증 성공 후:
python -B tools/github_inbox/autodev.py @commonArgs --enable-development --watch
```

설치 Issue 자체는 자동 실행되지 않는다. 기존 v2 수신기는 v3를 무시하므로 이번 교체는
로컬 Hermes에 링크를 한 번 전달해야 한다. 이후 지원되는 v3 개발 지시는 GitHub로 직접 전달한다.
종료·로그아웃·절전 시 멈추는 전경 프로세스다. 부팅 자동 실행·예약·서비스·절전 설정은 이 단계에서 변경하지 않는다.
main 자동 병합·배포·주문 실행·ZenBook 설치·비공개 프로젝트 자동 수정은 후속 범위다.

## 로컬 검증

Linux/Python 3.12에서 기존 33건 + 새 autodev 16건 = **49건 통과**.
새 검증은 실제 임시 Git 작업폴더·파일 적용·Python 테스트 프로세스를 사용한다.
AI 생성 및 GitHub 게시 API는 대역이다. 고정 인수 검사의 잘못된 구현 감지,
전송 실패 후 journal 복구와 모델 미재호출, 같은 커밋/PR 재사용, 브랜치 충돌,
범위·Python 계약 거부를 포함한다. 실제 AI5 설치·모델 생성·PR 왕복은 설치 후 별도로 확인한다.
