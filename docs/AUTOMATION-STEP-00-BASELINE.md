# AUTOMATION STEP 00 — 보안·개발 기준선

- 수행일: 2026-09-21
- 브랜치: `feat/automated-rebuild-20260921`
- 기준 커밋: `f41cd5ef7a0a4de457a82ddc8a33d858a38bc34c`

## 확인 결과

- 활성 구현은 `execution/` 16개 Python 파일과 `tests/` 19개 테스트 파일이다.
- `web/`, `contracts/`, `patterns/`, `adapters/`, `sync/`는 아직 없다.
- Windows에서 수행된 최신 기록은 98개 테스트 통과다.
- Linux Docker에서는 `execution/ownership.py`의 Windows 전용 `msvcrt` 때문에 전체 테스트를 실행할 수 없다.
- 공유 작업 트리는 CRLF 차이로 파일 171개가 변경된 것처럼 보였지만 `core.autocrlf=true` 적용 시 깨끗한 상태다.
- `.env`가 Git에 추적되고 있었고 실제 형식의 Telegram 및 계좌 관련 값이 들어 있었다. 값은 출력하지 않았다.

## 이번 단계 변경

- `.env`를 Git 추적 대상에서 제거하고 로컬 파일로 유지한다.
- `.env.example`에는 안전한 `RUN_MODE=PAPER` 기본값만 두고 비밀정보 필드는 빈 값으로 제공한다.
- `.gitattributes`에서 기본 LF와 Windows 스크립트 CRLF를 구분한다.
- 자동화 개발 단계와 실계좌 금지 경계를 문서화한다.

## 보안 후속 조치

이번 커밋은 이후 커밋에서 비밀값을 제거하지만 과거 Git 이력의 값을 삭제하지 않는다. 다음 조치는 사용자가 직접 수행하거나 별도로 승인해야 한다.

1. Telegram Bot 토큰 폐기 및 재발급
2. 저장된 계좌 비밀번호 변경
3. 새 비밀값은 로컬 `.env` 또는 전용 비밀 저장소에만 보관
4. 필요하면 별도 승인 후 Git 이력 정리와 강제 푸시

## 검증 기준

- `git ls-files .env` 결과가 비어 있어야 한다.
- `.env` 로컬 파일은 유지되며 `.gitignore`에 의해 무시돼야 한다.
- 신규 문서와 예제 파일에 실제 토큰·비밀번호가 없어야 한다.
- `core.autocrlf=true` 기준 작업 트리는 이번 단계 파일만 변경돼야 한다.

## 다음 단계

Vue 보드 개발 전에 Docker 개발 이미지에 지원되는 Node 런타임과 패키지 관리 도구를 준비한다. 웹은 mock-only로 시작하며 Python 주문 엔진이나 실계좌 API를 호출하지 않는다.
