"""Fixed host-side acceptance tests, outside model-editable paths."""
import importlib.util
from pathlib import Path
import sys
import unittest


class StatusContract(unittest.TestCase):
    def test_known_labels(self):
        for code, label in {"WAITING": "대기 중", "RUNNING": "개발 중", "TEST_FAILED": "검증 실패",
                            "PR_CREATED": "PR 작성 완료", "UNKNOWN": "확인 필요"}.items():
            with self.subTest(code=code):
                self.assertEqual(MODULE.describe(code), label)

    def test_unknown_string(self):
        for value in ("", "something", "running", "../secret"):
            with self.subTest(value=value):
                self.assertEqual(MODULE.describe(value), "확인 필요")

    def test_non_strings_rejected(self):
        for value in (None, 1, True, [], {}):
            with self.subTest(value=value), self.assertRaises(TypeError):
                MODULE.describe(value)


if __name__ == "__main__":
    directory = Path(sys.argv.pop(1)).resolve(strict=True)
    spec = importlib.util.spec_from_file_location("status_text", directory / "status_text.py")
    MODULE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(MODULE)
    unittest.main()
