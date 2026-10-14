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

## 다음 작업: R04 계속

R04 이력 TR 식별(`kt00007/kt00009/ka10076`, `POST /api/dostk/acnt`)은
`feature/rest-r04-history-spec`에 문서 경계로 기록했다. 전송 허용·원장 연결은
하지 않았고 `can_reconcile`은 false다. R02/R03 문서의 PC 검증 결과를 구분한다.
`execution.models.Scope`는 아직 virtual만 허용한다. 이 제한을 단순히 REST 문자열로 풀지 않는다.
다음은 모의계좌 실측(`probe_kiwoom_rest --execute-read-only --include-history`)으로
세 이력 TR의 실제 응답·페이지헤더를 확인하고, Q01/Q02/Q08 식별 근거를 확정한 뒤
REST 전용 scope를 설계한다.

## 다음 작업: R05 실증 실행

R05 실증 도구(`submit_paper_buy`, `verify_paper_linkage`)는 오프라인 검증했다.
[R05 기록](REST-R05-ORDER-DEMO.md) 순서대로 사용자 PC에서 미리보기·제출·연결
확인을 실행한다. 제출은 모의 1주 지정가 1회이며 자동 재시도·취소·원장 연결은 없다.

## R05 이후 차단 기록

R04 scope 게이트 이후는 실측 없이는 오프라인으로 진행하지 않는다.
R05 주문 dispatcher, R06 패턴·보호 연결, R07 무인 운영, R08 보드 인수는
모의계좌 실측(Q01/Q02/Q08 확정)과 허용된 주문 실증 뒤에 착수한다.
차단 사유와 재개 조건은 상태 JSON의 `external_pending`을 따른다.
현재 잔고/미체결 두 조회만으로 orders/fills 근거를 만들지 않는다.
Q01~Q11 REST 식별·수량 의미가 실제 근거로 확인되기 전 실제 dispatcher를 활성화하지 않는다.
주식체결 가격 수신은 주문체결 사실이 아니다. 거래일·세션을 수신시각에서 만들지 않는다.
가상 reconciliation을 실제 계좌 대조 완료로 재사용하지 않는다.

## 검사

개발 환경에 검사 도구가 없으면 기존 격리 개발 환경에
`python -m pip install pytest==9.1.1 ruff==0.16.7 basedpyright==1.40.2`로 준비한다.
실제 WebSocket 도구 의존성은 `tools/requirements-rest-probes.txt`로 별도 설치한다.

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
