import unittest

from app.utils.review_checks_display import (
    format_review_checks_notify_summary,
    format_review_checks_section,
)


class TestReviewChecksDisplay(unittest.TestCase):
    def test_all_pass_section(self) -> None:
        summary = {"checks_total": 2, "checks_passed": 2, "checks_failed": 0, "aggregate": "checks_passed"}
        results = [
            {"check_slug": "security", "check_name": "Security", "result": "pass", "summary": "ok"},
            {"check_slug": "style", "check_name": "Style", "result": "pass", "summary": "ok"},
        ]
        text = format_review_checks_section(review_iter=1, summary=summary, results=results)
        self.assertIn("Security", text)
        self.assertIn("2/2 passed", text)

    def test_fail_listed_first(self) -> None:
        results = [
            {"check_slug": "style", "check_name": "Style", "result": "pass", "summary": "ok"},
            {"check_slug": "security", "check_name": "Security", "result": "fail", "summary": "secret found"},
        ]
        text = format_review_checks_section(review_iter=1, summary={"checks_total": 2, "checks_passed": 1, "checks_failed": 1}, results=results)
        self.assertLess(text.index("Security"), text.index("Style"))

    def test_no_rows_returns_empty(self) -> None:
        self.assertEqual(format_review_checks_section(review_iter=1, summary=None, results=[]), "")

    def test_prerequisite_skip(self) -> None:
        results = [
            {
                "check_slug": "security",
                "check_name": "Security",
                "result": "skip",
                "error_code": "prerequisite_missing",
                "summary": "Prerequisite missing: diff",
            }
        ]
        text = format_review_checks_section(review_iter=1, summary={"checks_total": 1}, results=results)
        self.assertIn("prerequisite_missing", text)

    def test_notify_when_not_passed(self) -> None:
        text = format_review_checks_notify_summary(summary={"aggregate": "checks_failed", "checks_failed": 1, "checks_total": 2})
        self.assertIn("1 failed", text)

    def test_notify_empty_when_passed(self) -> None:
        self.assertEqual(format_review_checks_notify_summary(summary={"aggregate": "checks_passed"}), "")


if __name__ == "__main__":
    unittest.main()
