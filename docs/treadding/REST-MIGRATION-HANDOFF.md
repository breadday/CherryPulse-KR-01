# 다른 AI용 재개 지시서

대화 기억 없이 이 저장소에서 이어갈 수 있도록 작성했다. 최신 상태는 같은 폴더의
`REST-MIGRATION-STATUS.json`, 검증 결과는 `REST-MIGRATION-VERIFICATION.md`다.

## 시작

1. `git status --short`, `git branch --show-current`, `git log -5 --oneline` 확인.
2. 원격을 fetch하고 divergence를 확인한다. 사용자 변경은 보존한다.
   PR #3 병합 후 main에 이 기반이 있다면 최신 main에서 새 작업 브랜치를 만든다.
3. 루트 `AGENTS.md`, 전환 계획, 실행 계약·테스트 매트릭스·미확인 사항을 읽는다.
4. 상태 JSON에서 첫 미완료 작업을 선택하고 `in_progress`로 기록한다.
5. 관련 코드를 읽고 최소 단위부터 구현한다. 기존 가상 엔진과 실제 scope를 섞지 않는다.

## 다음 작업: R04

R02 인증·읽기 실행기와 R03 모의 WebSocket 관측/재접속 경계는 오프라인 검증했다.
실제 모의 계좌·장중 WebSocket은 미검증이다. R02/R03 문서의 PC 검증 결과를 구분한다.
`execution.models.Scope`는 아직 virtual만 허용한다. 이 제한을 단순히 REST 문자열로 풀지 않는다.
REST 조회 시작/종료 시각·원장 revision 경계·앱/계좌 별칭과 조회 종류별 완전성 모델은
`adapters/kiwoom_rest_evidence.py`에 오프라인 검증했다. [R04 기록](REST-R04-QUERY-EVIDENCE.md)을 읽고
주문/체결 이력 API 규격·범위를 확정해 읽기 경계를 확장한다. 현재 잔고/미체결 두 조회만으로 orders/fills 근거를 만들지 않는다.
Q01~Q11 REST 식별·수량 의미가 실제 근거로 확인되기 전 실제 dispatcher를 활성화하지 않는다.
주식체결 가격 수신은 주문체결 사실이 아니다. 거래일·세션을 수신시각에서 만들지 않는다.
가상 reconciliation을 실제 계좌 대조 완료로 재사용하지 않는다.

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

CherryPulse-KR-01의 REST 전환 작업을 최신 main에서 이어서 진행해.
AGENTS.md와 docs/treadding/REST-MIGRATION-HANDOFF.md, STATUS.json을 읽고,
첫 미완료 단계부터 계획·구현·테스트·검증·기록·한글 커밋·push를 반복해.
주문 전송 OFF를 유지하고 실제 증권사 검증이 필요한 부분은 구체적인 명령과 판정 기준을 남겨.
토큰이 부족해지면 안정된 작은 단위를 push하고 다음 작업을 기록해.
