# D01 설정·패턴·명령 계약 진행 기록

## 2026-09-26 desired·accepted·local applied 적용 경계

시작 기준은 `git fetch origin main` 뒤 `HEAD`와 `origin/main` 모두
`c147e69138b7551b8af0cad971812c31aa4636dd`, 브랜치 `main`, 작업 트리 clean이다.

기존 `ConfigInbox`와 `Ledger`는 서로 다른 SQLite 파일을 사용한다. 이 둘을
단일 원자 트랜잭션이라고 표현할 수 없다. 다음의 재개 가능한 교차 DB 상태로
구현했다.

1. `ConfigInbox.receive`는 명령 모델을 다시 검증하고 주입된 인증기의 검증
결과, 계좌/환경 범위, `CONFIG_WRITE`, 기대 버전, 만료 및 idempotency를
확인한 뒤 desired payload와 `ACCEPTED` 결정을 inbox 한 트랜잭션에 보관한다.
   인증 context 자체는 저장하지 않는다.
2. 수락만으로는 원장이나 감시 상태를 바꾸지 않는다. 적용 요청은 inbox에서
   먼저 `APPLYING`으로 기록한다.
3. 로컬 원장은 command ID와 digest를 가진 `AppliedConfig`와 해당 설정의
   `VirtualStopBinding`을 한 원장 트랜잭션에 기록한다. 같은 command ID/digest의
   재호출은 기존 원장 근거를 반환하고, ID 내용 충돌·버전 충돌은 거절한다.
   `Settings.version`은 실행 설정/체결 배정 버전이고 `Pattern.version`은 패턴
   자체의 버전이다. 둘을 같다고 가정하지 않으며, stop binding은 기존 fill
   assignment가 참조하는 settings version으로 기록한다. 원본 command digest는
   별도 inbox payload와 대조할 연결 근거다.
4. 원장 적용 결과를 받은 뒤에만 inbox를 `APPLIED`로 표시한다. inbox의
   `APPLIED`는 **로컬 설정 기록 완료**이고 감시 활성화나 주문 허가가 아니다.
   Settings가 강제하는 `monitoring_enabled=False`, `entry_enabled=False`는
   그대로 유지한다.

프로세스가 inbox의 `APPLYING` 기록 뒤 원장 기록 전에 종료되면 재시작 시
`resume_pending()`이 원장 적용을 다시 시도한다. 원장 기록 뒤 inbox 완료 표기
전에 종료된 경우에도 같은 command ID/digest를 원장에서 찾아 중복 적용하지
않고 inbox 상태를 수렴시킨다. 명확한 버전·scope 충돌은 `APPLY_BLOCKED`와
사유로 남기며, 재시도는 `retry_blocked=True`인 명시 호출만 허용한다. 로컬
계좌/실행 lease의 대조 gate가 닫혀 있을 때는 inbox를 `APPLYING`으로 바꾸지
않고 적용을 거부한다.

기존 holdings의 `StopRuleAssignment` 및 이전 규칙 binding은 수정·삭제하지
않는다. 새 설정은 새 local version/binding으로 추가되고, 기존 보유는 체결
당시 버전으로 조회된다. 실행 원장의 초기 암묵 버전 1과 desired inbox의
초기 기대 버전 0은 새 계좌·종목의 첫 적용에서만 대응시킨다. 이미 로컬
설정/규칙이 존재해 현재 버전이 기대 버전과 다르면 적용을 차단한다.

인증 제공자/검증기는 아직 없다. 기본 `ConfigInbox(path)`는
`CONFIG_AUTHENTICATION_UNAVAILABLE`로 fail-closed이고, caller가 만든 `Actor`
단독으로 수락을 만들 수 없다. `ConfigAuthenticator`는 신뢰된 ingress가
주입할 인터페이스일 뿐 실제 인증 구현이 아니다. 저장소의 수락 테스트는
test-only fake authenticator만 사용한다. 과거 스키마에서 Actor 주장만으로
`ACCEPTED`였던 행은 마이그레이션 후 `APPLY_BLOCKED` /
`LEGACY_AUTHENTICATION_UNVERIFIED`가 되고 accepted-version 계산에서 제외된다.
실제 인증된 재전달 또는 운영자 검토 전에는 이를 재개하지 않는다.

이 변경은 inbox와 원장 SQLite 파일에 대한 application protocol이며 두 파일
사이 원자성을 보장하지 않는다. 중간 상태는 inbox의 `APPLYING`/`APPLY_BLOCKED`
및 원장의 command ID/digest로 식별·재개한다. 운영 설정 DB에 마이그레이션을
실행하지 않았고 실제 인증 공급자·웹/Windows 동기화 연결도 구현하지 않았다.

### D01 상태와 검증

- **desired**: 검증된 `ConfigCommand` payload, 별도 inbox DB에 저장.
- **accepted**: inbox의 권한/범위·만료·기대 버전·멱등성 판정을 통과한 결정.
- **applying/applied**: 서로 다른 원장 적용 진행/로컬 영속 완료. applied만으로
  감시나 주문이 켜지지 않는다.
- 의미 있는 가상 검사: 기본 인증 차단, 인증 context 누락/실패, 범위 권한,
  만료·버전·중복·identity conflict, 역순 apply 차단 및 순서 수정 뒤 명시 재시도,
  inbox→원장 양쪽 commit 경계의 재시작, 기존 설정 충돌 보존, 기존 보유의
  규칙 버전 보존, inbox schema 이전 수락의 fail-closed 차단.

2026-09-26 Windows Python 3.10.8 32비트 결과:

| 명령 | 결과 |
|---|---|
| `py -3.10-32 -m pytest -q --tb=line --basetemp <고유 임시 경로> tests/test_settings_contract.py tests/test_config_apply.py tests/test_command_freshness.py` | 종료 0, **27 passed** |
| `py -3.10-32 -m pytest -q --tb=line --basetemp <고유 임시 경로>` | 종료 0, **177 passed, 4 subtests passed** (`8.37s`) |
| 변경 파일 Ruff check / format check | 각각 종료 0 |
| `py -3.10-32 -m execution` | 종료 0, 가상 데모 정상 |
| `git diff --check` | 종료 0 |

전체 `ruff check execution contracts tests`와 전체 format check는 기존
`tests/test_realtime_probe.py`의 기존 lint/format 진단으로 각각 종료 코드 1이다.
해당 파일은 이번 diff에서 수정하지 않았다. basedpyright는 설치되지 않아
미실행이다. 키움 실증·운영 DB·주문·배포는 실행하지 않았다.

**D01은 미완료**다. 다음에는 실제 신뢰 가능한 인증 제공자와 계좌/환경 권한
검증기를 연결하고, 인증된 환경에서만 inbox 입력이 가능하도록 배치해야 한다.
그 전까지 기본 inbox가 차단되는 것이 정상 동작이다. 이어서 Windows 3.10
32비트 고정 `.venv` 기반 회귀, 적용 경계 실패 주입/재시작 및 운영자 대조
경로를 검증하되 실제 계좌·운영 DB에는 실행하지 않는다.

## 2026-09-24 추가 검증

같은 계좌·환경에서 다른 종목의 명령 ID를 재사용하면 SQLite 고유 제약 오류 대신
`CONFLICT_CONFIG_COMMAND_IDENTITY`를 반환하도록 수신 조회 범위를 수정했다.
기존 명령의 재전달 결정은 그대로 유지한다. 변경 파일은 `contracts/inbox.py`,
`tests/test_settings_contract.py`다. Linux Python 3.12의 분리된 임시 검사
디렉터리에서 D01 검사 9개 통과, Ruff 통과, `git diff --check` 통과.
Windows 3.10 32비트 전체 검사, 외부 인증, 수신 결정과 실행 원장 적용의
원자적 연결은 수행하지 않았다. 실제 키움 API, 운영 DB, 배포는 건드리지 않았다.

- 기준: [남은 개발 작업 계획](NEXT-DEVELOPMENT-PLAN.md), `main`의 `f41cd5e` 기반 작업 공간
- 상태: **부분 구현**. 원하는 설정의 안전한 수신·보관 모델까지 구현했고, 엔진 적용과 외부 인증 연결은 미완료다.

사용자 결정(2026-09-24): 첫 손절은 고정 가격과 평균 매수가 대비 하락률을 모두 종목별 선택형으로 한다. 주문 방식은 시장가·지정가 설정형으로 설계한다. 첫 가상 손절은 최근 체결가와 확인된 매수 체결가의 수량 가중평균(수수료 제외)을 사용하고 시장가를 우선한다. 필요한 실행 정책이 완성되기 전에는 감시를 활성화하지 않는다. 후속 판단기 결과는 [D03 진행 기록](D03-VIRTUAL-STOP-PROGRESS.md)을 참조한다.

## 이번에 구현한 범위

`contracts/settings.py`는 종목별 불변 버전의 손절 패턴, 설정, 명령 ID·멱등 키·기대 버전·만료 시각, 인증된 주체의 계좌/환경/권한 범위를 검증한다. 예시 규칙은 가격 이하와 평균 매수가 대비 하락률이다. 시세 기준, 거래 세션, 주문 유형, 실제 손절 수치는 정해지지 않았으므로 `monitoring_enabled`와 `entry_enabled`는 모두 `False`만 허용한다.

`contracts/inbox.py`는 별도 SQLite 파일에 수신 명령과 결정, 주체 ID를 한 트랜잭션으로 기록한다. 같은 명령의 재전달은 기존 결정을 반환한다. 같은 키 또는 ID에 다른 내용이 들어오면 충돌을 거절한다. 새 명령은 권한·범위·만료·기대 버전·버전 증가를 확인한다. 여기서의 `ACCEPTED`는 **원하는 설정이 수신되어 보관됨**만 의미한다. `execution/`의 `AppliedConfig`는 기존 가상 버전 검사이며 이 수신 결과와 연결하지 않았다. 따라서 이 코드로 감시나 주문이 시작되지 않는다.

## 명령 신뢰 경계

현재 `Actor`는 호출자가 이미 검증한 신원 주장이다. `ConfigInbox`를 인터넷 요청에 직접 노출할 수 없다. 인증 토큰 검증, 계좌별 권한 조회, 서명 또는 세션 검증, 취소된 권한 반영, 안전한 비밀 저장은 클라우드/Windows 동기화 어댑터에서 아직 구현되지 않았다. 권한 없는 재전달은 기존 결정도 반환하지 않는다. 현재 inbox DB는 별도 개발용 파일로만 사용하며 운영 원장 이전 도구가 아니다.

## 다음 작업 전에 결정할 내용

| 항목 | 필요한 결정·근거 | 미결정 중 처리 |
|---|---|---|
| 손절 기준 | 최근 체결가와 수수료 제외 체결가 평균은 결정됨. 시세 최대 허용 지연과 가격 근거 원장 연결 필요 | 감시 활성화 차단 |
| 주문 | 시장가 우선은 결정됨. 미체결/거절·거래 시간 정책 필요 | 주문 실행 차단 |
| 보유 보호 인계 | 설정 교체 시 기존 보유에 적용할 버전 | 기존 보호 규칙 임의 변경 금지 |
| 명령 인증 | 웹 로그인·계좌별 권한, Windows 수신자의 신뢰 증명 | 외부 명령 수신 활성화 차단 |
| DB 통합 | desired/accepted/applied 상태와 기존 원장 버전의 안전한 연결·이전 | 숫자 버전만으로 패턴 적용 주장 금지 |

## 검사 범위

2026-09-24 재검사: `tests/test_settings_contract.py`와 `tests/test_stop_evaluation.py`를 임시 검사 디렉터리에 복사해 `PYTHONPATH=.`으로 실행했고 **12개 통과**했다. 원래 `tests/`에서 실행하면 공통 `conftest.py`가 Windows 전용 `msvcrt`를 불러오므로 수집 단계에서 중단된다. 평균 매수가와 시세 가격의 비유한 값 거절 검사도 포함했다. 이번 실행 환경에는 `ruff` 명령이 없어 정적 검사는 재실행하지 못했다. `git diff --check`는 통과했다. Windows 3.10 32비트 `.venv`의 전체 회귀 검사, 실제 인증·키움·웹 검증은 수행하지 않았다.

다음은 이 계약의 입력과 적용 상태를 구분하는 화면 골격(D02), 그리고 독립된 가상 손절 평가와 보호 의무(D03)다. D01을 완료로 표시하기 전 실제 인증 어댑터와 설정 적용 버전의 원자적 연결을 구현해야 한다.

## 2026-09-25 진행 재개 시 적용 차단 확인

현 코드에는 별도 DB의 `ConfigInbox`와 실행 원장의 `AppliedConfig`/가상
손절 규칙 저장이 존재하지만, 서로 다른 저장소를 연결하는 인증된 적용 서비스는
없다. 적용 연결을 추가하려면 인증 주체를 생성하는 신뢰 경계(인증 제공자,
계좌·환경 권한), 계정과 원장 scope 매핑, 적용 실패·재시작 뒤 desired/accepted/
applying/applied 상태 복구 계약이 먼저 정해져야 한다. `Settings`가 허용하는
비활성 패턴을 그대로 `VirtualStopBinding`에 적용하면 실행 후보 조회 경로에서
규칙으로 취급될 수 있으므로 단순 버전 복사로 연결하지 않는다.

이 정보와 경계 없이 외부 명령을 받아들이거나 적용 완료로 표시하는 구현은
진행하지 않는다. 필요한 결정이 마련되기 전에는 기존 명령 수신 계약 검증과
비활성 로컬 UI까지만 유지하며, `ACCEPTED`는 희망 설정 보관을 뜻한다.
