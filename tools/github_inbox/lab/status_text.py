LABELS = {
    "WAITING": "대기 중",
    "RUNNING": "개발 중",
    "TEST_FAILED": "검증 실패",
    "PR_CREATED": "PR 작성 완료",
    "UNKNOWN": "확인 필요",
}


def describe(code):
    if not isinstance(code, str):
        raise TypeError("code는 문자열이어야 합니다.")
    return LABELS.get(code, LABELS["UNKNOWN"])
