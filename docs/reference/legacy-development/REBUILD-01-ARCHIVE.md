# REBUILD-01 파일 보관·개발 참고

- 2026-09-13, `main`, HEAD `5922a45b97971769481a2bc096e8dd22dd2194df` 기준.
- 최신 요청에 따라 기존 방식의 파일을 활성 경로에서 제거하고 `back/legacy-2026-09-13/`으로 이동했다. 영구 삭제는 하지 않았다.
- 이동: 최상위 대상 50개, 내부 파일 101개. 기존 AGENTS.md는 별도 `AGENTS.previous.md`로 복사한 뒤 활성 지침을 새 방향으로 수정했다.
- 상세 원본 경로·이동 경로·바이트 수·SHA-256: [MOVE-MANIFEST.json](../back/legacy-2026-09-13/MOVE-MANIFEST.json).

## 분류와 재사용 판단

| 보관 대상 | 새 개발에서의 취급 |
|---|---|
| backtest/, 전략 분석·비교·최적화 스크립트 | 폐기 예정. 성과 검증·후보 승격 재도입 금지 |
| selectors/, strategies/, strategy/, universe_manager.py | 구 선정·전략 경로 폐기. 필요한 순수 조건 계산만 별도 검토 |
| main_live.py, engine.py, config_live.py, auto_session_manager.py | 구 진입점·조정·설정은 보관. 새 execution/ 구조에 계약 기준으로 재작성 |
| broker/ | 키움 I/O 재사용 후보. 주문 ID·접수·취소·체결 필드 의미를 검증한 후 adapters/로 편입 |
| core/ | 주문·포지션 모델 참고. 요청 상태 분리·배정·예약·멱등성은 새 계약으로 구성 |
| infra/ | SQLite·알림 참고. 새 원장의 트랜잭션·원자성 검증 후 필요한 기능만 편입 |
| utils/, data/*.py | 로깅·시세·CSV 계산 참고. 점수·추천 경로 제외 |
| 루트 *.bat, *.ps1 및 나머지 *.py | 구 실행·준비·검증·백업 명령 보관. 새 실행 안내로 사용 금지 |
| ARCHITECTURE.md, RESPONSIBILITIES.md, readme.txt, 다중 전략.md | 구 설계·운영 안내 보관. 활성 README.md·AGENTS.md·REBUILD 문서로 교체 |
| docs/PROJECT_STATUS_2026-09-09.md, docs/SOURCE_ANALYSIS.md | 과거 상태·분석 참고. 현재 구현 또는 새 요구사항으로 간주하지 않음 |
| requirements.txt, .env.example, condition_list_dump.json, inspect_select_db.txt | 구 환경·생성물 보관. 새 의존성·입력 설정은 이후 작성 |

전체 소스 묶음을 보관한 이유는 기존 main_live→engine→broker/core/infra 및 config 의존성이 얽혀 있기 때문이다. 일부 모듈만 활성 경로에 남겨 잘못된 구 실행을 가능하게 하지 않는다. 필요한 기능까지 영구 폐기한 것은 아니다.

## 보존 범위

기준 개발방향 문서, .git, .gitignore, .env, data/daily, data/sample, _backups 및 기타 운영 자료는 이번 이동 대상에서 제외했다. .env와 백업 내용은 출력하지 않았다. 기존 docs/harness 4개 문서와 Herdr/OpenCode 계획의 사용자 삭제 상태는 유지했다. 삭제된 파일을 복원하거나 back으로 재생성하지 않았다.

저장소 전용 .agents 스킬은 보존한다. 활성 AGENTS는 새 요구사항이 과거 스킬의 스윙·성과검증 지침보다 우선함을 명시한다. back 안의 pycache는 구 파일과 함께 보관됐으며 새 소스에 편입하지 않는다.

## 복구와 추후 삭제

manifest에서 필요한 원본 경로와 보관 경로를 확인하고, 신규 파일과 충돌하지 않는 별도 검토 경로로 복사해 비교한다. 새 구현 위에 보관본을 일괄 덮어쓰지 않는다. 보관본은 이동 전 해시를 기록했다. 복구 시 파일 SHA-256을 manifest와 비교할 수 있다.

추후 영구 삭제 조건: 필요한 공통 기능 편입 완료, 주문·체결·복구 검증 완료, 보유·미체결 인계와 운영 데이터 보존 확인, 복원 필요 없음 확인, 사용자 삭제 요청. 그 전에는 보관한다.

## 완료 범위와 남은 조사

파일 수준 정리와 의존성의 주요 경로 확인을 완료했다. 전 함수 호출 그래프, 실제 계좌 잔고, 실행 중 프로세스, Windows 예약 작업, 키움 환경, 외부 경로·DB 의존성은 확인하지 않았다. 따라서 REBUILD-01 전체 현황 조사를 완료했다고 표시하지 않는다. 이동은 프로세스 종료·예약 작업 해제·계좌 보호 인계를 수행하지 않는다.

## 보관 검증 — 2026-09-14

manifest의 이동 파일101개를 실제 보관 파일 SHA-256과 비교해 불일치0을 확인했다. 새 안내·계약·계획 문서의 로컬 링크19개도 검사해 끊어진 링크0이다. 이동 전 기록한 파일 바이트를 보존했으며 새 엔진 실행 검증을 의미하지 않는다.

## 현행 활성 경로 정적 확인 — 2026-09-25

- `execution/`, `contracts/`, `adapters/`의 Python 파일 23개를 Python 3.10 AST로
  읽어 보관 루트(`back/`)와 구 실행 모듈(`main_live`, `engine`, 구
  `broker/core/selectors/strategies/infra`) import 및 `subprocess.run`/`Popen`/
  `os.system`/`os.startfile` 호출을 검사했다. 해당 import와 프로세스 호출은
  0건이었다. 단순 문자열 검색의 1건은 `execution/query_evidence.py` docstring
  설명으로 AST import나 호출이 아니다.
- 현재 `verify_kiwoom_com.py`는 COM 컨트롤 생성·해제, `verify_kiwoom_connection.py`는
  `GetConnectState()` 관측, `verify_kiwoom_readonly.py`는 사용자가 직접 로그인·계좌를
  선택한 뒤 제한된 읽기 전용 TR만 호출하도록 작성돼 있다. 읽기 전용 허용 목록은
  `opw00018`, `opt10075`; `opw00007`은 규격 미확인으로 거절한다. 이 조사에서는
  스크립트를 실행하지 않았고 키움 로그인·조회도 하지 않았다.
- `subprocess` 사용은 검색상 보관된 `back/` 코드와 테스트의 가상 데모·잠금 경합
  검사에서 발견됐다. 보관본의 외부 실행 의미를 현재 활성 경로에 편입하지 않았다.
- 같은 날 Windows에서 읽기 전용으로 예약 작업 이름/경로/동작 문자열, 프로세스
  이름, 서비스 이름을 `CherryPulse|main_live|selector_7am|daily_strategy|
  auto_session_manager|verify_kiwoom` 대상으로 검색해 모두 0건이었다. 실행 인수,
  서비스 구성, 계좌·비밀값은 출력하지 않았다. 이는 조사 시점의 로컬 관측이다.
- 이 확인은 현재 저장소와 지정 키워드의 로컬 조사 범위다. 다른 이름으로 등록된
  서비스·예약 작업, 다른 사용자/PC, 외부 바로가기·실행 래퍼 및 실제 계좌 상태는
  확인되지 않았다. REBUILD-01 전체 현황은 계속 미완료다.
