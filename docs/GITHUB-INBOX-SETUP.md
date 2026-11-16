# GitHub 작업 전달함 — 1단계 연결 시험

2026-11-17. 중앙 PC는 AI5. 전달함은 `breadday/CherryPulse-KR-01`이다.
이 저장소는 공개 저장소다. Issue·댓글에 계좌·키·토큰·로컬 경로·파일명·diff·비공개 저장소 정보를 기록하지 않는다.

## 현재 구현 범위

이 수신기는 Python 표준 라이브러리와 기존 GitHub CLI만 사용한다.
60초마다 일반 스크립트로 확인하며 AI 모델·유료 API·GitHub Actions·호스팅을 호출하지 않는다.
`ping` 및 선택적인 CherryPulse Git 상태 집계만 지원한다.
자연어 작업 실행, Hermes/Codex 호출, 코드 수정, 주문, 예약, 배포는 아직 지원하지 않는다.
기존 REST 상태·원장·실행기는 변경하지 않는다.

소유자 breadday가 작성한 열린 Issue 중 제목이 `[hermes-task]`로 시작하고
본문 전체가 아래 JSON 규격인 것만 처리한다. 댓글·PR·다른 작성자·임의 명령은 실행하지 않는다.

```json
{"version":1,"target":"AI5","action":"ping"}
```

target은 AI5 또는 ZENBOOK, action은 ping 또는 status이다.
수신기 시작 시 실제 호스트 이름이 BREADDAY_AI5 또는 ZENBOOK인지 검사한다.
status 대상 경로는 Issue에서 받지 않고 시작 인자로 고정한다.
선택한 프로젝트 origin이 CherryPulse와 정확히 일치해야 하며 파일 내용은 읽지 않는다.

## AI5에서 최초 1회 설치

기존 Kiwoom·CherryPulse의 미커밋 작업 폴더에서 pull/checkout하지 않는다.
별도 경로 예: `D:\hermes-local\github-inbox-bootstrap`.
이미 같은 경로가 있으면 덮어쓰지 말고 상태를 먼저 확인한다.
본 PR의 정확한 커밋을 별도 clone에서 검토한다. 토큰은 명령·파일에 붙여넣지 않고 기존 gh 인증을 사용한다.

```powershell
hostname
gh auth status --hostname github.com
git clone --branch feat/github-inbox-bootstrap --single-branch https://github.com/breadday/CherryPulse-KR-01.git D:\hermes-local\github-inbox-bootstrap
Set-Location D:\hermes-local\github-inbox-bootstrap\tools\github_inbox
python -B -m unittest discover -s . -p "test_receiver.py" -v
python -B receiver.py --target AI5 --dry-run
python -B receiver.py --target AI5
```

python은 사용 가능한 64-bit Python 절대 경로로 대체해도 된다.
프로젝트 거래 엔진 의존성 설치는 필요 없다. 기존 프로젝트의 런타임은 변경하지 않는다.
현재 ChatGPT 실행 환경이 없어 위 테스트·Windows 실행은 아직 미실행이다.
테스트가 실패하면 실제 수신을 시작하지 말고 실패를 기록한다.
GitHub 로그인은 breadday여야 한다. 인증정보는 보고하지 않는다.

단발 시험 후 동일 Issue에 transport=OK, llm_called=false, orders_called=false 댓글이 생기는지 확인한다.
재실행 시 완료 댓글 마커로 같은 요청을 건너뛴다. 대상별 로컬 파일 잠금으로 중복 수신기를 막는다.
댓글 POST 중 네트워크가 끊기면 재조회 후 재시도한다. GitHub 측 반영 지연 등에서 엄밀한 exactly-once는 보장하지 않는다.
따라서 이 경로에 부작용 있는 명령 실행을 추가하지 않는다.

연결 성공 후 상시 확인은 아래 전경 프로세스로 실행한다.

```powershell
python -B receiver.py --target AI5 --watch
```

Ctrl+C로 종료한다. 창·프로세스가 닫히거나 PC가 절전이면 멈춘다.
부팅 자동 실행·Windows 예약 작업은 아직 등록하지 않는다.
이 대화도 종료 후 GitHub 결과를 저절로 계속 감시하지 않는다. 사용자가 결과 확인을 요청하면 조회한다.

## ZenBook과 개발 실행으로 확대할 때

ZenBook에서는 같은 수신기와 target ZENBOOK을 사용하고, status에만 기존 CherryPulse 경로를 시작 인자로 지정할 수 있다.
AI5 설치 시험과 별개이며 지금 ZenBook의 개발 세션·Gateway·REST 브랜치는 변경하지 않는다.
2단계는 설치된 Hermes/Codex 인증 및 실제 명령을 로컬에서 검증한 뒤 설계한다.
ChatGPT 구독 로그인과 사용량 기반 API 키를 구분하고, 유료 API 자동 전환은 구성하지 않는다.
자연어 작업을 받아 기존 파일을 수정하는 단계에는 전용 작업공간·중복 실행 방지·실행 이력·시간 제한·결과 회수 검증이 추가로 필요하다.
현재 ping 시험의 성공을 개발 자동화 완료로 보고하지 않는다.
