# ruff: noqa: PT009

from __future__ import annotations

import unittest

from src.line_tools import unique_clean_lines


class UniqueCleanLinesTests(unittest.TestCase):
    def test_case_variants_keep_the_first_cleaned_spelling(self) -> None:
        self.assertEqual(
            unique_clean_lines(["  Alpha ", "alpha", "BETA", " beta "]),
            ["Alpha", "BETA"],
        )

    def test_empty_lines_are_skipped_and_input_order_is_preserved(self) -> None:
        self.assertEqual(unique_clean_lines([" ", "first", "", "second", "first"]), ["first", "second"])


if __name__ == "__main__":
    unittest.main()
