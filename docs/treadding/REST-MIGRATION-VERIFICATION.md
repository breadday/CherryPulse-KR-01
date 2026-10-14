# REST 전환 첫 검증 — 2026-10-14

기준 main `1ec7966`, Linux Python 3.12.14, pytest 9.1.1, Pydantic 2.13.5,
Ruff 0.17.0, basedpyright 1.40.2, Node 24.19.0.
기존 Windows/Python3.10 의존성 파일은 변경하지 않았다. 이 환경 검사가 Windows 인증은 아니다.

## 구현

- `adapters/kiwoom_rest_readonly.py`: 잔고 kt00018·미체결 ka10075만 허용,
  필수 입력·행·return_code·페이지 헤더 검증, 커서 반복/페이지 제한/예외에 불완전 표시.
- `adapters/kiwoom_rest_transport.py`: 고정 모의 호스트·계좌 조회 URL만 사용,
  외부 토큰 공급자·timeout·리디렉션 거절·자동 재시도 없음. 토큰 발급·속도제어는 미구현.
- `tests/rest/test_readonly.py`: synthetic 응답 검사. 계좌 배정·체결 반영·주문 기능 없음.
- `tools/verify_rest_migration.py`: 고정 오프라인 검사와 원자적 JSON 보고서.
- `.github/workflows/rest-migration.yml`: 오프라인 검사·Windows 전체 회귀와 데모.

## 실행 결과

| 검사 | 결과 |
|---|---|
| `python -m pytest --confcutdir=tests/rest tests/rest -q` | 28 passed |
| `node --test web/board/board.test.js` | 23 passed |
| 신규 4파일 Ruff check/format | 통과 |
| `git diff --check` | 통과 |
| `python -m pytest -q` 전체 | 수집 차단: 기존 Windows 전용 msvcrt, Linux에서 미검증 |
| 기존 전체 Ruff | 변경 전 47 errors, 이번 범위에서 미수정 |
| 기존 basedpyright | 변경 전 108 errors, 이번 범위에서 미수정 |

신규 검증기는 실패 시 비정상 종료하며 skipped 전체 엔진 검사를 성공으로 표시하지 않는다.
모의 transport 검사는 opener를 주입한 오프라인 검사다. 개발 중 monkeypatch 위치 오류로
synthetic token을 사용한 모의 서버 요청 1회가 시도되었다. 유효 키·계좌 정보는 사용하지 않았고
TRANSPORT_UNCONFIRMED로 종료했다. 위치를 수정한 최종 검사는 실제 네트워크를 호출하지 않는다.
증권사 인증·실시세·잔고·체결·주문 확인 근거 없음. 운영 DB/Windows 예약/배포 변경 없음.

## 미완료와 재개

R02부터 인계 문서 순서대로 진행한다. R01 모의 연결은 실제 사용을 위한 완성형 실행기가 아니다.
Windows CI의 실제 결과·원격 SHA·병합 상태는 아래 후속 기록에 추가한다.

## 원격 후속 검증

- PR: https://github.com/breadday/CherryPulse-KR-01/pull/3
- CI: https://github.com/breadday/CherryPulse-KR-01/actions/runs/38510395015
- Windows Python 3.10 x64: **210 passed**, 가상 데모 통과. 사용자 PC·32비트 OCX 검증은 아님.
- Linux Python 3.10: REST 28개·보드 23개·신규 파일 Ruff 0.16.7·format·diff 통과.
- 최초 Windows CI는 results 부모 경로 미생성으로 81 passed/129 errors.
  workflow에 폴더 생성을 추가한 후 위 결과로 해결했다. 실패 기록도 보존한다.
- 위 CI는 구현+workflow 수정 커밋 기준. 이 후속 기록은 증권사 계좌 검증을 추가하지 않는다.
- 인증·속도제어·WebSocket·실제 주문 연결 미구현은 상태 JSON에 유지한다.

## R02/R03 및 R04 준비 후속 검증

기준 main623f09f, feature/rest-auth-stream.
R02 모의 인증·갱신·pacing·읽기 도구, R03 모의 WebSocket 관측·재접속·신선도,
R04 조회 interval/revision 범위 경계를 구현했다.

- 로컬 REST/WS 113 passed, 보드23, 신규 production6파일 basedpyright0, Ruff/format 통과.
- R02 CI https://github.com/breadday/CherryPulse-KR-01/actions/runs/38513088606
- R03 CI https://github.com/breadday/CherryPulse-KR-01/actions/runs/38513857671
- R03 Windows Python3.10 전체284 및 가상 데모 통과. R04 후속 전체 검사는 PR #4 CI에서 확인한다.
- https://github.com/breadday/CherryPulse-KR-01/pull/4
- 테스트는 socket 연결을 차단했다. 유효한 키/토큰·계좌 없이 synthetic 응답만 사용했다.
- REST/WS 도구 기본 실행 network=false를 실제 확인했다. websockets15.0.1 설치 및
  사용 connect 옵션의 실제 라이브러리 signature 존재를 확인했다.
- 실제 로그인·계좌조회·시세·주문·운영 DB·사용자 PC 예약 변경은 수행하지 않았다.
- 실제 계좌/세션·주문/체결 mapping·원장 연결·무인 운영은 미완료다.

최종 로컬 회귀: REST/WS 115 passed. 인증 실패 뒤 두 번째 조회 호출 0,
비정상 payload 요약 실패 처리 검사를 추가했다. 새 production 타입0·보드23·Ruff/format 통과.
최종 Windows 전체 회귀 결과는 PR #4의 최신 head CI가 기준이다.
