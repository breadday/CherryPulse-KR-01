# 다른 AI용 재개 지시서

대화 기억 없이 이 저장소에서 이어갈 수 있도록 작성했다. 최신 상태는 같은 폴더의
`REST-MIGRATION-STATUS.json`, 검증 결과는 `REST-MIGRATION-VERIFICATION.md`다.

## 시작

1. `git status --short`, `git branch --show-current`, `git log -5 --oneline` 확인.
2. 원격을 fetch하고 divergence를 확인한다. 사용자 변경은 보존한다.
3. 루트 `AGENTS.md`, 전환 계획, 실행 계약·테스트 매트릭스·미확인 사항을 읽는다.
4. 상태 JSON에서 첫 미완료 작업을 선택하고 `in_progress`로 기록한다.
5. 관련 코드를 읽고 최소 단위부터 구현한다. 기존 가상 엔진과 실제 scope를 섞지 않는다.

## 다음 작업: R02

모의 서버 전용 토큰 발급/만료 관리와 읽기 실행기를 구현한다. 비밀 키는 로컬 환경에서만
읽고 repr/log/보고서에 포함하지 않는다. 인증 실패 시 주문 재시도 기능을 추가하지 않는다.
현재 `PaperReadOnlyTransport`는 토큰 공급자만 주입받고 토큰 발급·속도 제어가 없다.
R02에서 이를 해결한 뒤에만 계좌 반복 조회 도구에 연결한다. R01은 조회 전체 대조나 계좌
배정 완료를 의미하지 않는다. 페이지 헤더가 빠지면 불완전으로 남기는 현재 정책을 유지한다.
R03 WebSocket은 official 규격 확인·synthetic replay부터 진행한다.

## 검사

```powershell
python tools/verify_rest_migration.py
python -m pytest -q --basetemp=results/rest-full-pytest
python -m execution
python -m ruff check .
python -m ruff format --check .
python -m basedpyright
```

전체 원장 검사는 Windows가 필요하다. Linux에서 msvcrt 에러를 제거하려고 잠금을
가짜 처리하거나 검사 성공으로 바꾸지 않는다. Linux의 REST 검사만 필요하면:
`python -m pytest --confcutdir=tests/rest tests/rest -q`.
검증 도구의 결과 파일은 실행 산출물로 Git 제외; 결과 요약은 검증 Markdown에 기록한다.

## 단계 종료·중단 직전

변경 파일·명령·exit code·미검증·차단 이유·다음 정확한 행동을 기록한다.
JSON과 인계 문서를 갱신하고 `git diff --check` 후 작은 한글 커밋으로 push한다.
원격 CI 결과를 기록하고 완료 상태로 올린다. 기존 Ruff/type baseline 오류와 이번 오류를 구분한다.
작업 중단 시 진행 중 단계와 수정 파일을 기록한다. 검증되지 않은 코드를 완료로 올리지 않는다.

## 다음 AI에 붙여넣을 문장

CherryPulse-KR-01의 refactor/kiwoom-rest 작업을 이어서 진행해.
AGENTS.md와 docs/treadding/REST-MIGRATION-HANDOFF.md, STATUS.json을 읽고,
첫 미완료 단계부터 계획·구현·테스트·검증·기록·한글 커밋·push를 반복해.
주문 전송 OFF를 유지하고 실제 증권사 검증이 필요한 부분은 구체적인 명령과 판정 기준을 남겨.
토큰이 부족해지면 안정된 작은 단위를 push하고 다음 작업을 기록해.
