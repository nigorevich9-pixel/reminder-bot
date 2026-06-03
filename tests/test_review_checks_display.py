"""Unit tests for app.utils.review_checks_display (reminder-bot PR4)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Allow `from app.utils.review_checks_display import ...`.
sys.path.insert(0, str(HERE.parent))

from app.utils.review_checks_display import (  # noqa: E402
    format_review_checks_notify_summary,
    format_review_checks_section,
)


# --------------------------------------------------------------------------- #
# Section formatter
# --------------------------------------------------------------------------- #


class TestFormatSection(unittest.TestCase):
    def test_no_summary_returns_empty(self) -> None:
        self.assertEqual(format_review_checks_section(summary=None), "")
        self.assertEqual(format_review_checks_section(summary={}), "")

    def test_iteration_in_header(self) -> None:
        section = format_review_checks_section(
            summary={
                "review_iter": 2,
                "aggregate": "checks_passed",
                "checks_total": 1,
                "checks_passed": 1,
            },
            check_results=[
                {"check_slug": "security", "result": "pass", "summary": "ok"},
            ],
        )
        self.assertTrue(section.startswith("Review checks (iteration 2)"))

    def test_all_pass_no_failure_first(self) -> None:
        rows = [
            {"check_slug": "a", "check_name": "A", "result": "pass", "summary": "ok"},
            {"check_slug": "b", "check_name": "B", "result": "pass", "summary": "ok"},
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_passed", "checks_total": 2, "checks_passed": 2},
            check_results=rows,
        )
        self.assertIn("\u2705", section)
        self.assertNotIn("\u274C", section)
        self.assertNotIn("\u26A0", section)

    def test_fail_listed_first(self) -> None:
        rows = [
            {"check_slug": "pass-a", "check_name": "Pass A", "result": "pass", "summary": "ok"},
            {"check_slug": "fail-b", "check_name": "Fail B", "result": "fail", "summary": "leak"},
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_failed", "checks_total": 2, "checks_failed": 1},
            check_results=rows,
        )
        self.assertLess(section.index("Fail B"), section.index("Pass A"))

    def test_prereq_skip_renders_icon_and_error_code(self) -> None:
        rows = [
            {
                "check_slug": "docs",
                "check_name": "Docs",
                "result": "skip",
                "error_code": "prerequisite_missing",
                "summary": "",
            }
        ]
        section = format_review_checks_section(
            summary={
                "review_iter": 1,
                "aggregate": "checks_skipped_due_to_prerequisite",
                "checks_total": 1,
                "checks_skipped_due_to_prerequisite": 1,
            },
            check_results=rows,
        )
        self.assertIn("\u23ED", section)
        self.assertIn("Docs", section)
        self.assertIn("prerequisite_missing", section)

    def test_error_row_renders_warning_icon(self) -> None:
        # When summary is present, error_code is NOT shown (avoid double noise).
        rows = [
            {
                "check_slug": "x",
                "check_name": "X",
                "result": "error",
                "error_code": "timeout",
                "summary": "model timed out",
            }
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_degraded", "checks_total": 1, "checks_error": 1},
            check_results=rows,
        )
        self.assertIn("\u26A0", section)
        self.assertIn("model timed out", section)

    def test_error_row_with_no_summary_uses_error_code(self) -> None:
        rows = [
            {
                "check_slug": "y",
                "check_name": "Y",
                "result": "error",
                "error_code": "timeout",
                "summary": "",
            }
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_degraded", "checks_total": 1, "checks_error": 1},
            check_results=rows,
        )
        self.assertIn("timeout", section)

    def test_no_check_results_uses_aggregate_line(self) -> None:
        section = format_review_checks_section(
            summary={
                "review_iter": 3,
                "aggregate": "checks_failed",
                "checks_total": 4,
                "checks_passed": 2,
                "checks_failed": 1,
                "checks_error": 1,
                "checks_skipped": 0,
                "checks_skipped_due_to_prerequisite": 0,
            },
            check_results=None,
        )
        self.assertIn("Aggregate: checks_failed", section)
        self.assertIn("passed=2", section)
        self.assertIn("failed=1", section)
        self.assertIn("error=1", section)
        self.assertIn("total=4", section)

    def test_summary_truncates(self) -> None:
        rows = [
            {
                "check_slug": "long",
                "check_name": "Long",
                "result": "fail",
                "summary": "x" * 500,
            }
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_failed", "checks_total": 1, "checks_failed": 1},
            check_results=rows,
        )
        # Single line: no \n inside a check line.
        for line in section.splitlines():
            if "Long" in line:
                # The summary part is 79 chars + ellipsis = 80 chars max
                self.assertLessEqual(len(line.split("\u2014 ", 2)[-1]), 80)

    def test_summary_with_newlines_uses_first_line_only(self) -> None:
        rows = [
            {
                "check_slug": "multi",
                "check_name": "Multi",
                "result": "fail",
                "summary": "first line\nsecond line\nthird",
            }
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_failed", "checks_total": 1, "checks_failed": 1},
            check_results=rows,
        )
        self.assertIn("first line", section)
        self.assertNotIn("second line", section)
        self.assertNotIn("third", section)

    def test_fallback_name_when_missing(self) -> None:
        rows = [
            {"check_slug": "", "check_name": "", "result": "pass", "summary": "ok"},
        ]
        section = format_review_checks_section(
            summary={"review_iter": 1, "aggregate": "checks_passed", "checks_total": 1, "checks_passed": 1},
            check_results=rows,
        )
        # Falls back to "?" when neither slug nor name is provided.
        self.assertIn("? \u2014", section)


# --------------------------------------------------------------------------- #
# Notify summary
# --------------------------------------------------------------------------- #


class TestNotifySummary(unittest.TestCase):
    def test_no_summary_returns_empty(self) -> None:
        self.assertEqual(format_review_checks_notify_summary(summary=None), "")
        self.assertEqual(format_review_checks_notify_summary(summary={}), "")

    def test_passed_returns_empty(self) -> None:
        text = format_review_checks_notify_summary(
            summary={"aggregate": "checks_passed", "checks_passed": 3, "checks_failed": 0, "checks_error": 0}
        )
        self.assertEqual(text, "")

    def test_failed_returns_summary(self) -> None:
        text = format_review_checks_notify_summary(
            summary={"aggregate": "checks_failed", "checks_passed": 1, "checks_failed": 1, "checks_error": 0}
        )
        self.assertIn("Review checks: checks_failed", text)
        self.assertIn("passed=1", text)
        self.assertIn("failed=1", text)
        self.assertIn("error=0", text)

    def test_degraded_returns_summary(self) -> None:
        text = format_review_checks_notify_summary(
            summary={"aggregate": "checks_degraded", "checks_passed": 0, "checks_failed": 0, "checks_error": 2}
        )
        self.assertIn("Review checks: checks_degraded", text)

    def test_truncates_to_max(self) -> None:
        text = format_review_checks_notify_summary(
            summary={"aggregate": "checks_failed", "checks_passed": 1, "checks_failed": 1, "checks_error": 0},
            max_chars=20,
        )
        self.assertLessEqual(len(text), 25)  # ellipsis may add a few chars
        self.assertTrue(text.endswith("\u2026"))


if __name__ == "__main__":
    unittest.main()
