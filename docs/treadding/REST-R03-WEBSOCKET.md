# R03 — 모의 WebSocket 관측 경계

2026-10-14, `feature/rest-auth-stream`. 구현은 독립 코드이며 공식 SDK를 복사하지 않았다.
공식 조사 SHA `953e5dbff123f437ab4d11a78a95191a685eb51f`의 stock_trade_async 예제,
ws_client 및 websockets 공식 sync client 문서를 참고했다.
https://websockets.readthedocs.io/en/15.0.1/reference/sync/client.html

## 구현·검증

- `kiwoom_rest_stream.py`: 명시적 LOGIN 성공→REG 성공→enrolled 0B 가격 순서.
  missing/boolean return_code, 잘못된 FID10/20, 다른 종목/주문체결00는 가격으로 반영하지 않는다.
- FID10 부호는 가격 방향 표기이므로 절댓값으로 관측하고 FID20은 HHMMSS clock만 보관한다.
  거래일/시장 세션/체결 고유키는 만들지 않는다. 이 가격을 execution Fill로 반영하지 않는다.
- `kiwoom_rest_ws.py`: 고정 모의 TLS URL, 1~120초 제한, PING echo,
  수집 구간은 최대120초이며 인증·연결·종료에는 별도 timeout 시간이 더해질 수 있다.
  transport 오류 뒤 최대 2회 재접속(설정 상한 3), 재로그인·재등록, 종료 시 close.
  재접속 시 과거 가격을 usable로 유지하지 않는다. 이전 관측 건수는 감사용으로 보존한다.
- 로그인/등록 실패는 재시도하지 않고 종료한다. 토큰 발급 실패도 같은 실행에서 재발급 반복하지 않는다.
- 연결마다 독립 비출력 logger로 DEBUG 프레임의 토큰 노출을 막는다.
- `probe_kiwoom_ws.py`: 기본 네트워크 OFF, 출력은 요약만. 종료 후 연결은 끊긴 상태다.
- optional library는 tools/requirements-rest-probes.txt의 websockets 15.0.1로 고정했다.
  `typing-extensions`도 REST 어댑터의 직접 의존성으로 함께 고정했다. REST/WS는
  Python 3.10에서 32/64비트 모두 가능하며 Windows OCX 의존성과 분리한다.
  기존 pyproject/uv.lock은 변경하지 않았다.
- 로컬 REST/WS **102 passed**, 보드23, production REST 5파일 basedpyright 0 errors,
  신규 파일 Ruff/format 통과. R02 원격 CI는 Windows241 및 가상 데모 통과.
  최종 R03 Windows 검사 결과는 PR/검증 기록에 이어서 반영한다.

## PC에서 확인

저장소 루트의 Python 3.10 실행 환경에서(32/64비트 모두 가능):

```powershell
py -3.10 -m pip install -r tools/requirements-rest-probes.txt
py -3.10 -m tools.probe_kiwoom_ws
py -3.10 -m tools.probe_kiwoom_ws 005930 --seconds 30 --execute-read-only
```

실제 실행 전 R02 문서의 모의 전용 환경변수 2개를 현재 프로세스에 설정한다.
첫 명령은 의존성 설치, 둘째는 network=false 확인, 셋째는 명시적 모의 읽기 호출이다.
장중 실행 결과 exit0, quotes_observed>0, fresh_before_close=true가 가격 관측 성공이다.
로그인/등록만 성공하거나 NO_QUOTE이면 exit1이다. 이는 주문·보유 보호 검증 성공이 아니다.
시장 종료·실시간 데이터 제공 범위·인증 문제는 실제 결과로 구분해야 한다.
`connected_after_capture=false`가 정상 종료다. 영구 감시 서비스는 아직 아니다.

## R04 연결 전 남은 근거

| 항목 | 현재 | 필요 근거 |
|---|---|---|
| 계좌·앱·환경 범위 | 모의 host 고정, 실제 앱/계좌 미확인 | 지정 앱/계좌 읽기 결과 |
| 가격/시각 payload | synthetic 0B 재생 | 장중 실제 프레임 필드 확인 |
| 거래일·세션 | 미구현 | 거래소·서버 근거, 0s 장상태 규격·실증 |
| 조회 대조 | 잔고·미체결만 | 주문·체결·페이지·시각·revision 경계 |
| 주문/체결 식별 | 미구현 | Q01/Q02/Q08 원문·연결 근거 |
| 수량·취소·여력 | 미구현 | Q03~Q07 단계별 근거 |
| 재접속 후 매매 재개 | 허용 안 함 | 조회 대조·UNKNOWN 해결·계좌 잠금 |

세션 추정, 가상 조회를 실제 근거로 승격, token/request_id를 broker execution key로
사용하는 변경은 하지 않았다. 실제 계좌 결과가 없어도 R04의 별도 근거 모델·가상 검사는 가능하다.
