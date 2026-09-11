# TASK-027 TEST

## 실행 결과

```text
py -3.8-32 -B -m pytest -q tests/test_task027_live_account_guard.py
2 passed in 0.07s
```

```text
py -3.8-32 -B -m pytest -q
113 passed, 18 skipped in 158.80s (0:02:38)
```

## 검증 범위

- 주문 허용 모드의 계좌번호 누락 차단
- 10자리 숫자가 아닌 명시적 계좌번호 차단
- Python 3.8 32-bit 전체 회귀
- 실제 Kiwoom 로그인·계좌 조회·주문 미실행
