import unittest

from app.utils.human_review_display import format_needs_review_cta


class HumanReviewDisplayTests(unittest.TestCase):
    def test_cta_includes_close_task_wording(self) -> None:
        text = format_needs_review_cta(task_id=123)
        self.assertIn("закрыть задачу", text)
        self.assertIn("/run 123", text)
        self.assertIn("на доработку", text)
        self.assertIn("/ask 123", text)
        self.assertIn("Merge в main не выполняется автоматически", text)

    def test_cta_with_pr_url(self) -> None:
        text = format_needs_review_cta(task_id=5, pr_url="https://github.com/o/r/pull/1")
        self.assertIn("PR: https://github.com/o/r/pull/1", text)


if __name__ == "__main__":
    unittest.main()
