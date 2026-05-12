이제부터는 이 프로젝트에서 AI에게 작업을 시킬 때 **하네스 문서를 기준표로 쓰면 됩니다.**

가장 쉽게 쓰는 방법은 이겁니다.

```text
AGENTS.md 먼저 보고 작업해줘.
일봉 후보 기반 스윙 매매 원칙은 유지하고,
docs/harness/CHANGE_CHECKLIST.md 기준으로 검증까지 해줘.
```

즉, 앞으로 나한테 요청할 때 이렇게 말하면 됩니다.

```text
AGENTS.md 기준으로 확인하고 수정해줘.
오늘 로그 보고 문제 있으면 docs/harness 설계 원칙에 맞게 고쳐줘.
```

실행할 때는 배치파일 3개만 기억하면 됩니다.

```text
run_build_daily_strategy_snapshot.bat
```

전날/아침에 일봉 후보를 만듭니다.

```text
run_main_live.bat
```

일봉 후보를 기준으로 실전형 모의투자를 실행합니다.

```text
run_verify_harness.bat
```

코드 수정 후 전체 기본 검증을 합니다.

운영 순서는 이렇게 보면 됩니다.

```text
1. 일봉 데이터 최신화
2. run_build_daily_strategy_snapshot.bat 실행
3. condition_snapshot.json 후보 확인
4. run_main_live.bat 실행
5. 장 종료 후 로그 확인
6. 코드 수정이 있으면 run_verify_harness.bat 실행
```

하네스 문서의 역할은 이겁니다.

- `AGENTS.md`: AI가 제일 먼저 읽어야 하는 입구 문서
- `DESIGN_PRINCIPLES.md`: 이 프로그램이 어떤 방향으로 가야 하는지
- `FILE_RESPONSIBILITY.md`: 어떤 파일이 어떤 책임을 갖는지
- `CHANGE_CHECKLIST.md`: 수정 후 뭘 검증해야 하는지
- `AI_WORKFLOW.md`: AI가 어떤 순서로 작업해야 하는지

쉽게 말하면, 앞으로는 AI가 “그때그때 감으로 코딩”하지 못하게 하고, **정해진 설계 원칙 안에서만 수정하게 만드는 장치**입니다.