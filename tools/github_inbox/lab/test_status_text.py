import unittest
from status_text import describe


class DescribeTests(unittest.TestCase):
    def test_known_codes(self):
        for code, expected in (
            ("WAITING", "대기 중"),
            ("RUNNING", "개발 중"),
            ("TEST_FAILED", "검증 실패"),
            ("PR_CREATED", "PR 작성 완료"),
            ("UNKNOWN", "확인 필요"),
        ):
            with self.subTest(code=code):
                self.assertEqual(describe(code), expected)

    def test_unspecified_strings(self):
        for code in ("", "OTHER", "waiting", " WAITING", "WAITING ", "대기 중"):
            with self.subTest(code=code):
                self.assertEqual(describe(code), "확인 필요")

    def test_non_strings_raise_type_error(self):
        for code in (None, True, 0, 1.5, b"WAITING", [], {}, ()):
            with self.subTest(code=code):
                with self.assertRaises(TypeError):
                    describe(code)
