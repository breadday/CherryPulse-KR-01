# R02 — 모의 토큰·읽기 실행기

2026-10-14, 기준 `623f09f`, 브랜치 `feature/rest-auth-stream`.

## 구현

- `adapters/kiwoom_rest_auth.py`: 모의 고정 토큰 URL, 메모리 캐시,
  만료 1분 전 갱신, 단일 갱신 잠금, 시계 역행 시 차단, 비밀 repr 제외.
- 토큰 발급과 조회에 같은 RequestPacer를 사용한다. 세션 내 직렬 1.1초 간격,
  실패 요청도 간격을 소비한다. 다른 프로세스/PC의 호출량까지 조정하지 않는다.
- 모의 읽기 transport: 응답 1MiB 상한·리디렉션 금지·자동 재시도 없음.
- `tools/probe_kiwoom_rest.py`: 기본 네트워크 OFF, 명시 옵션으로 조회,
  계좌번호·원문·키·토큰 출력 없음. 종료코드 0은 두 조회의 페이지 완전성뿐이다.
- 테스트는 실제 socket 연결을 차단한다. synthetic token/keys만 사용한다.
- 새 REST production 3파일 basedpyright 0 errors, REST 오프라인 59 passed.
  기존 보드 23 passed, 신규 Ruff/format 통과. Windows CI 결과는 PR에 기록한다.

## 사용자 PC 읽기 검증

저장소 루트에서 Python 3.10 환경을 사용한다. REST는 아키텍처에 종속되지 않으며
PyQt·OCX 로그인 창은 사용하지 않는다. 모의 조회의 기본 검사:
`py -3.10 -m tools.probe_kiwoom_rest` 실행, network=false가 기대값이다.
실제 호출을 위해 **모의 전용** 앱 키를 아래 이름으로 설정한다.
저장 위치: Windows 11 사용자 환경 변수 (`setx` 또는 제어판 사용자 계정 메뉴).
한 번 저장하면 새 프로세스·예약 작업에서 읽힌다.
값은 문서·채팅·Git·보고서에 절대 기록하지 않는다. AI도 값을 요구하지 않으며
존재 여부만 true/false로 확인한다. 기존 KIWOOM_* 변수를 사용하지 않으므로
다른 프로젝트 계좌 설정과 혼용되지 않는다.

- `CHERRYPULSE_PAPER_APP_KEY`
- `CHERRYPULSE_PAPER_APP_SECRET`

주의: `KIWOOM_APP_KEY`/`KIWOOM_APP_SECRET` 이름으로는 읽지 않는다.
다른 프로젝트와 혼용 방지가 목적이며, 두 이름이 모두 있으면 본 문서 이름을 우선한다.

출력 감사 규칙: 모든 도구 보고서는 키·토큰·계좌번호·주문번호 원문을 포함하지
않는다. 숫자 4자리 이상은 마스킹하고, 검토는 true/false·사유 코드로만 한다.
테스트는 합성 비밀값이 출력에 없음을 검사한다.

```powershell
py -3.10 -m tools.probe_kiwoom_rest --execute-read-only --max-pages 3
```

성공: exit 0, PAPER, orders_enabled=false, 두 queries.complete=true.
실패: exit 1과 사유. 인증/네트워크 오류는 UNCONFIRMED이며 계좌가 비었다는 뜻이 아니다.
PAGE_LIMIT_REACHED이면 페이지가 남았고 불완전하다. 필요하면 상한 10까지 늘려 재조회한다.
이력 3건 실측은 `--include-history`를 붙인다. 성공 기준은 5건 모두 complete=true다.
토큰·키 입력이 없어도 오프라인 개발과 테스트는 진행할 수 있다.

## 한계

실계좌 및 실주문 경로 없음. 사용자 PC/모의 서버 실행은 이번 개발에서 수행하지 않았다.
조회 결과로 관리 배정을 만들지 않고 전체 계좌 대조 완료로 표시하지 않는다.
인증 실패는 같은 조회를 자동 재전송하지 않는다. 다음 명시 호출에서만 새 갱신을 시도한다.
토큰은 종료 때 메모리에서 사라진다. 무인 운영·계좌별 여러 프로세스 잠금은 R04/R07 과제다.
