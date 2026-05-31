import unittest

from app.utils.work_plan_display import (
    WorkPlanDisplayMode,
    format_work_plan_section,
    format_work_item_line,
    resolve_work_plan_display,
)


def _plan_row(detail_id: int, plan_status: str, **content_extra) -> dict:
    content = {"plan_status": plan_status, "goal": "Fix auth flow", "work_items": []}
    content.update(content_extra)
    return {"detail_id": detail_id, "content": content}


def _wi(wi_id: str, title: str, status: str = "pending") -> dict:
    return {"id": wi_id, "title": title, "status": status}


class TestWorkPlanDisplay(unittest.TestCase):
    def test_no_plans_returns_none_section(self) -> None:
        display = resolve_work_plan_display(task_status="RUNNING", plans=[])
        self.assertEqual(display.mode, WorkPlanDisplayMode.NONE)
        self.assertEqual(format_work_plan_section(task_id=1, task_status="RUNNING", display=display), "")

    def test_needs_user_read_latest_draft_after_rejected(self) -> None:
        plans = [
            _plan_row(3, "draft", work_items=[_wi("wi-1", "Step 1")]),
            _plan_row(2, "rejected"),
            _plan_row(1, "draft", work_items=[_wi("wi-1", "Old step")]),
        ]
        display = resolve_work_plan_display(task_status="NEEDS_USER_READ", plans=plans)
        self.assertEqual(display.mode, WorkPlanDisplayMode.SHOW_PLAN)
        self.assertEqual(display.detail_id, 3)

    def test_needs_user_read_latest_rejected_not_older_draft(self) -> None:
        plans = [
            _plan_row(2, "rejected"),
            _plan_row(1, "draft", work_items=[_wi("wi-1", "Old step")]),
        ]
        display = resolve_work_plan_display(task_status="NEEDS_USER_READ", plans=plans)
        self.assertEqual(display.mode, WorkPlanDisplayMode.REPLAN_PENDING)
        section = format_work_plan_section(task_id=42, task_status="NEEDS_USER_READ", display=display)
        self.assertIn("План отклонён", section)
        self.assertNotIn("Old step", section)

    def test_running_latest_rejected_not_older_approved(self) -> None:
        plans = [
            _plan_row(2, "rejected"),
            _plan_row(
                1,
                "approved",
                work_items=[_wi("wi-1", "Done step", "done"), _wi("wi-2", "Current", "in_progress")],
            ),
        ]
        display = resolve_work_plan_display(task_status="RUNNING", plans=plans)
        self.assertEqual(display.mode, WorkPlanDisplayMode.REPLAN_PENDING)
        section = format_work_plan_section(task_id=7, task_status="RUNNING", display=display)
        self.assertIn("План отклонён", section)
        self.assertNotIn("Current", section)
        self.assertNotIn("Done step", section)

    def test_running_latest_approved_progress(self) -> None:
        plans = [
            _plan_row(
                4,
                "approved",
                work_items=[
                    _wi("wi-1", "Inspect", "done"),
                    _wi("wi-2", "Apply patch", "in_progress"),
                    _wi("wi-3", "Verify", "pending"),
                ],
            ),
        ]
        display = resolve_work_plan_display(task_status="RUNNING", plans=plans)
        self.assertEqual(display.mode, WorkPlanDisplayMode.SHOW_PLAN)
        section = format_work_plan_section(task_id=5, task_status="RUNNING", display=display)
        self.assertIn("План работ (approved, #4):", section)
        self.assertIn("▶ wi-2 — Apply patch [in_progress]", section)
        self.assertIn("Current: wi-2 — Apply patch", section)

    def test_needs_user_read_draft_cta(self) -> None:
        plans = [_plan_row(183, "draft", work_items=[_wi("wi-1", "Inspect")])]
        display = resolve_work_plan_display(task_status="NEEDS_USER_READ", plans=plans)
        section = format_work_plan_section(task_id=123, task_status="NEEDS_USER_READ", display=display)
        self.assertIn("План работ (draft, #183):", section)
        self.assertIn("План ждёт вашего approve.", section)
        self.assertIn("/run 123", section)
        self.assertIn("/ask 123", section)

    def test_unknown_item_status_renders_as_is(self) -> None:
        line_blocked = format_work_item_line(_wi("wi-1", "Blocked step", "blocked"), is_current=False)
        line_alien = format_work_item_line(_wi("wi-2", "Alien step", "paused_by_alien"), is_current=True)
        self.assertIn("[blocked]", line_blocked)
        self.assertIn("[paused_by_alien]", line_alien)

    def test_more_than_ten_items_truncated(self) -> None:
        items = [_wi(f"wi-{i}", f"Step {i}") for i in range(1, 13)]
        plans = [_plan_row(1, "draft", work_items=items)]
        display = resolve_work_plan_display(task_status="NEEDS_USER_READ", plans=plans)
        section = format_work_plan_section(task_id=1, task_status="NEEDS_USER_READ", display=display)
        self.assertIn("wi-10", section)
        self.assertNotIn("wi-11", section)
        self.assertIn("… ещё 2 шагов", section)


if __name__ == "__main__":
    unittest.main()
