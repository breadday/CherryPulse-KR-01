# REBUILD-01 운영 환경 확인

- 확인일: 2026-09-14. 저장소 main, HEAD `5922a45b97971769481a2bc096e8dd22dd2194df`.
- 범위: 파일·레지스트리·프로세스·예약 작업 읽기 전용 조사. 로그인·주문·서비스 중지·설치·환경변수 변경 없음.

## 1. 확인 결과

| 대상 | 확인 결과 | 의미와 한계 |
|---|---|---|
| 키움 설치 | C:/OpenAPI 존재, khopenapi.ocx 파일 버전1.0.0.1 | 파일 버전만으로 최신 서버 호환성 확정 불가 |
| OCX 아키텍처 | PE machine 0x014C, 32비트 | 동일 프로세스에서 사용하는 Python/Qt도 대응 아키텍처 필요 |
| COM 등록 | KHOPENAPI.KHOpenAPICtrl.1 및 WOW6432Node CLSID 등록 존재, InprocServer32가 C:/OpenAPI/KHOpenAPI.ocx | 등록 존재 확인이며 COM 생성·로그인 테스트 아님 |
| KOA Studio | KOAStudioSA.exe 존재, 파일 버전1.0.0.1 | 실행하지 않음 |
| 로컬 TR 자료 | opt10075.enc, opt10076.enc, opw00007.enc, opw00018.enc 존재 | 내용·조회 의미·서버 응답은 아직 검증 안 함 |
| 프로젝트 .venv | 없음 | 새 프로젝트의 재현 가능한 환경 구성 필요 |
| 현재 명령 탐색 | python 명령 미발견, py.exe 있음; py -0p는 등록 Python 없음으로 출력 | 실제 Python 미설치를 뜻하지 않음 |
| Python 3.10.8 | 사용자 Programs/Python/Python310-32/python.exe, PE32, PyQt5·QAxContainer.pyd 존재 | 신규 로컬 키움 호환 검사 후보. 패키지 import·OCX 생성은 미검증 |
| Python 3.8.10 | 사용자 Programs/Python/Python38-32/python.exe, PE32, PyQt5·QAxContainer.pyd 존재 | 기존 호환 비교 후보, 새 기준으로 자동 선택하지 않음 |
| Python 3.12.10 | 사용자 Programs/Python/Python312/python.exe, PE64, 해당 위치 PyQt5·QAxContainer 없음 | 현재32비트 OCX와 동일 프로세스 구성 후보에서 제외 |
| 실행 프로세스 | Python/키움 관련 이름 조회에서 관측 없음. 프로젝트 문자열 매칭은 언어 서버와 조사용 PowerShell만 관측 | 조사 시점의 관측이며 이후 실행 부재 보장 아님 |
| 예약 작업 | CherryPulse/main_live/selector_7am/daily_strategy/auto_session_manager를 Action에서 검색해0건 | 다른 이름의 간접 실행 스크립트·서비스·다른 PC까지 부재 보장 아님 |
| 운영 DB | %LOCALAPPDATA%/CherryPulse-KR-01/cherry_pulse.sqlite3 존재 | 내용 미열람. 보유·미체결 없음으로 해석 금지 |

최초 제한된 조회에서 WMI·예약 작업 및 사용자 Python 폴더 접근이 거절되어, 읽기 전용 권한 확장 후 재조회했다. 최종 결과는 성공한 재조회 기준이다. 프로세스 명령 인수·계좌·비밀값은 출력하거나 문서에 저장하지 않았다. venv 템플릿 내부 python.exe는 독립 설치 수에 포함하지 않았다.

## 2. 보관 실행 경로 확인

- run_main_live.bat → run_daily_prepare_and_main_live.bat → 데이터 다운로드·snapshot 생성·검증 → main_live.py의 구 실행 흐름을 확인했다.
- 여러 배치는 .venv가 없으면 python 명령으로 대체한다. 현재 세션에는 둘 다 준비되지 않아 구 배치를 재사용할 근거가 없다.
- a_run_am_selector_7am.bat는 select_stocks_7am.py를 참조한다. 이는 현재 보관 목록에서 발견되지 않은 구 의존성이며 새 후보 선정 기능으로 복원하지 않는다.
- auto_session_manager.py는 trade-script와 monitor-script를 subprocess로 실행하는 구 진입점이다. 새 실행 주체에 편입하지 않는다.
- engine.py는 set_fill_callback(on_fill), get_positions/get_pending_orders, 여러 place_order 경로와 cancel_order를 사용한다. 신규 단일 dispatcher로 옮길 때 여러 제출 경로가 남지 않도록 확인해야 한다.

이 조사는 주요 실행 경로와 외부 환경의 부분 조사다. 전 함수 호출 그래프·모든 외부 서비스·다른 PC·계좌 인계를 완료한 것은 아니다.

## 3. 다음 작업에 사용할 결정

1. 새 로컬 환경은 명시적 Python 경로를 사용한다. 런처 등록이나 PATH를 임의 변경하지 않는다.
2. 3.10.8 32비트 설치를 첫 호환 검사 후보로 삼는다. 현재 패키지를 무조건 복제하거나 최신 버전으로 일괄 올리지 않는다.
3. 패키지 버전·import·COM 생성의 무주문 검사 후 가상환경을 고정한다. 이 문서는 그 검사가 통과했다는 뜻이 아니다.
4. 실제 DB·계좌 관리량은 Q11 절차로 별도 대조한다. 파일 이동이나 프로세스 부재를 청산 완료로 사용하지 않는다.

연결: [계획](CherryPulse-KR-01-Rebuild-Plan.md), [API 근거](REBUILD-02-API-EVIDENCE.md), [미확인 사항](REBUILD-02-OPEN-QUESTIONS.md).

## 후속: 프로젝트 환경 구성 완료

2026-09-14 후속 작업에서 .venv를 구성했다. Python3.10.8 32비트와 고정된 Qt 패키지의 import, 키움 COM 생성·해제, 의존성 일관성, 오프라인 잠금 동기화를 확인했다. 위 초기 조사 표의 '.venv 없음'은 구성 전 관측이다. 현재 구성·명령·결과는 [개발 환경](DEVELOPMENT-ENVIRONMENT.md)을 따른다. 로그인·주문은 하지 않았다.
