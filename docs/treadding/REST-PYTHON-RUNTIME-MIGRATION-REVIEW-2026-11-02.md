# REST Python 런타임 전환 결과

갱신일: 2026-11-02
상태: 구현 및 로컬 오프라인 검증 완료. 원격 CI 확인은 미완료.

> 최종 결정 갱신 (2026-11-11): 이 검토의 대안 비교를 종료하고 **64-bit Python 3.15 REST/WebSocket 전용**으로 확정했다. COM/ActiveX CLI는 활성 실행에서 제외됐다. 아래 내용은 당시 런타임 전환 검토 기록이며, 현재 적용 기준은 `REST-MIGRATION-PLAN.md`와 `DEVELOPMENT-ENVIRONMENT.md`다.

## 결정

- 프로젝트 실행·검증 기준은 64-bit Python 3.15 (`>=3.15,<3.16`)이다.
- REST 조회는 공식 HTTP API 계약, 실시간 수신은 공식 WebSocket 계약을 따른다.
- REST 런타임, CI, 잠금 의존성, R045 실행기는 동일한 Python 기준을 사용한다.
- 구형 개발 계획과 실행 기록은 `docs/reference/legacy-development/` 아래 보관한다. 해당 자료는 이력 참고용이며 활성 실행 지침이 아니다.

## 반영 범위

- `pyproject.toml`, `uv.lock`, `tests/test_python_runtime_contract.py`
- `.github/workflows/rest-migration.yml`
- `scripts/r045-morning-run.cmd`, `run-paper-demo.bat`
- `tools/requirements-rest-probes.txt`
- 활성 개발 문서와 이번 전환 결과 문서

## 확인된 로컬 결과

- Python 3.15.2 x64에서 전체 pytest: 373 passed.
- `tools/verify_rest_migration.py`: 6/6, REST 테스트 168 passed, Ruff check/format 통과, REST adapter basedpyright 0 errors.
- Node worker/board 테스트: 63 passed.
- `npm run build`: Wrangler dry-run 성공.
- `git diff --check`: 통과.

## 미완료 경계

- GitHub Actions에서 변경 branch의 CI 성공 여부를 아직 확인하지 않았다.
- 지정 PC의 예약 작업은 새 venv에서 실행하지 않았다.
- 계좌 실측, 장중 데이터, 주문, 취소, 배포는 수행하지 않았다. `orders_enabled=false`를 유지한다.

외부 검증을 소프트웨어 테스트 결과로 대체하지 않는다. 다음 단계는 활성 문서·스크립트 참조 전수 정리, 전체 로컬 검증, 변경 파일 선별 커밋/push, 원격 CI 확인이다.
