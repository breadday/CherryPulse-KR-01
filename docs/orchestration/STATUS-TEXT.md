# 상태 코드 한글 안내

`tools/github_inbox/lab/status_text.py`의 `describe(code)`는 상태 코드 문자열을 받아 한글 안내 문자열을 반환하는 순수 함수입니다.

| 입력 | 반환값 |
| --- | --- |
| `"WAITING"` | `"대기 중"` |
| `"RUNNING"` | `"개발 중"` |
| `"TEST_FAILED"` | `"검증 실패"` |
| `"PR_CREATED"` | `"PR 작성 완료"` |
| `"UNKNOWN"` | `"확인 필요"` |

## 사용법

`status_text`를 가져올 수 있는 위치에서 다음과 같이 사용합니다.

```python
from status_text import describe

message = describe("RUNNING")
```

위 예제의 `message` 값은 `"개발 중"`입니다. 미지정 문자열과 빈 문자열은 모두 `UNKNOWN`에 해당하는 `"확인 필요"`를 반환합니다. 문자열이 아닌 값을 전달하면 `TypeError`가 발생합니다.

## 한계

코드는 대소문자와 공백을 포함하여 정확히 비교합니다. 대소문자 변환이나 공백 제거는 하지 않습니다. 예를 들어 `"running"`과 `" RUNNING"`은 모두 `"확인 필요"`로 처리합니다.

이 함수는 전달된 코드를 안내 문구로 변환할 뿐, 실제 작업 상태를 조회하거나 변경하지 않습니다. 외부 의존성, 파일 및 네트워크 접근, 입출력, 브로커, 인증, subprocess를 사용하지 않습니다.

## 테스트

`test_status_text.py`는 표준 `unittest`로 모든 지정 코드의 반환값, 미지정 문자열 처리, 문자열이 아닌 입력의 `TypeError` 계약을 검증하도록 작성되어 있습니다.

`tools/github_inbox/lab` 디렉터리에서 다음 명령으로 테스트를 실행할 수 있습니다.

```text
python -m unittest test_status_text
```

이 변경을 작성하는 과정에서 코드를 실행하거나 테스트 결과를 확인하지 않았습니다.
