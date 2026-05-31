from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


MAX_DISPLAY_WORK_ITEMS = 10

WORK_ITEM_IN_PROGRESS = "in_progress"
WORK_ITEM_DONE = "done"
WORK_ITEM_PENDING = "pending"


class WorkPlanDisplayMode(str, Enum):
    NONE = "none"
    SHOW_PLAN = "show_plan"
    REPLAN_PENDING = "replan_pending"


@dataclass(frozen=True)
class WorkPlanDisplay:
    mode: WorkPlanDisplayMode
    detail_id: int | None = None
    content: dict | None = None


def get_in_progress_work_item(work_items: list | None) -> tuple[str | None, dict | None]:
    if not isinstance(work_items, list):
        return None, None
    for item in work_items:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status == WORK_ITEM_IN_PROGRESS:
            wi_id = item.get("id")
            if isinstance(wi_id, str) and wi_id.strip():
                return wi_id.strip(), item
    return None, None


def _plan_status(plan_row: dict | None) -> str | None:
    if plan_row is None:
        return None
    content = plan_row.get("content")
    if not isinstance(content, dict):
        return None
    status = content.get("plan_status")
    return status if isinstance(status, str) and status.strip() else None


def _first_plan_with_status(plans: list[dict], status: str) -> dict | None:
    for row in plans:
        if _plan_status(row) == status:
            return row
    return None


def resolve_work_plan_display(*, task_status: str, plans: list[dict]) -> WorkPlanDisplay:
    if not plans:
        return WorkPlanDisplay(mode=WorkPlanDisplayMode.NONE)

    latest = plans[0]
    latest_status = _plan_status(latest)

    if latest_status == "rejected":
        return WorkPlanDisplay(mode=WorkPlanDisplayMode.REPLAN_PENDING)

    if task_status == "NEEDS_USER_READ" and latest_status == "draft":
        detail_id = latest.get("detail_id")
        content = latest.get("content") if isinstance(latest.get("content"), dict) else None
        return WorkPlanDisplay(
            mode=WorkPlanDisplayMode.SHOW_PLAN,
            detail_id=int(detail_id) if isinstance(detail_id, int) else None,
            content=content,
        )

    if latest_status == "approved":
        detail_id = latest.get("detail_id")
        content = latest.get("content") if isinstance(latest.get("content"), dict) else None
        return WorkPlanDisplay(
            mode=WorkPlanDisplayMode.SHOW_PLAN,
            detail_id=int(detail_id) if isinstance(detail_id, int) else None,
            content=content,
        )

    fallback = _first_plan_with_status(plans, "approved") or _first_plan_with_status(plans, "draft")
    if fallback is None:
        return WorkPlanDisplay(mode=WorkPlanDisplayMode.NONE)

    detail_id = fallback.get("detail_id")
    content = fallback.get("content") if isinstance(fallback.get("content"), dict) else None
    return WorkPlanDisplay(
        mode=WorkPlanDisplayMode.SHOW_PLAN,
        detail_id=int(detail_id) if isinstance(detail_id, int) else None,
        content=content,
    )


def _item_title(item: dict) -> str:
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    desc = item.get("description")
    if isinstance(desc, str) and desc.strip():
        text = desc.strip()
        if len(text) > 60:
            return text[:57] + "..."
        return text
    wi_id = item.get("id")
    if isinstance(wi_id, str) and wi_id.strip():
        return wi_id.strip()
    return "?"


def _item_status_label(item: dict) -> str:
    status = item.get("status")
    if isinstance(status, str) and status.strip():
        return status.strip()
    return WORK_ITEM_PENDING


def _marker_for_item(*, status: str, is_current: bool) -> str:
    if is_current or status == WORK_ITEM_IN_PROGRESS:
        return "▶"
    if status == WORK_ITEM_DONE:
        return "✓"
    return "·"


def format_work_item_line(item: dict, *, is_current: bool) -> str:
    wi_id = item.get("id")
    wi_id_str = wi_id.strip() if isinstance(wi_id, str) and wi_id.strip() else "?"
    status = _item_status_label(item)
    marker = _marker_for_item(status=status, is_current=is_current)
    return f"  {marker} {wi_id_str} — {_item_title(item)} [{status}]"


def _format_plan_body(*, content: dict, detail_id: int | None, task_status: str) -> list[str]:
    plan_status = content.get("plan_status")
    plan_status_str = plan_status if isinstance(plan_status, str) and plan_status.strip() else "unknown"
    header = f"План работ ({plan_status_str}, #{detail_id}):" if detail_id is not None else f"План работ ({plan_status_str}):"
    lines = [header]

    goal = content.get("goal")
    if isinstance(goal, str) and goal.strip():
        lines.append(f"Goal: {goal.strip()}")

    work_items = content.get("work_items")
    in_progress_id, in_progress_item = get_in_progress_work_item(work_items if isinstance(work_items, list) else None)

    if isinstance(work_items, list) and work_items:
        lines.append("")
        lines.append("Items:")
        shown = work_items[:MAX_DISPLAY_WORK_ITEMS]
        for item in shown:
            if isinstance(item, dict):
                wi_id = item.get("id")
                is_current = isinstance(wi_id, str) and wi_id.strip() == in_progress_id
                lines.append(format_work_item_line(item, is_current=is_current))
        remaining = len(work_items) - len(shown)
        if remaining > 0:
            lines.append(f"  … ещё {remaining} шагов")

        if in_progress_id and in_progress_item is not None:
            lines.append("")
            lines.append(f"Current: {in_progress_id} — {_item_title(in_progress_item)}")

    if task_status == "NEEDS_USER_READ" and plan_status_str == "draft":
        lines.extend(
            [
                "",
                "План ждёт вашего approve.",
            ]
        )

    return lines


def format_work_plan_section(*, task_id: int, task_status: str, display: WorkPlanDisplay) -> str:
    if display.mode == WorkPlanDisplayMode.NONE:
        return ""

    if display.mode == WorkPlanDisplayMode.REPLAN_PENDING:
        return (
            "План отклонён, ожидается новая версия…\n"
            f"Отправить feedback снова: /ask {task_id} <feedback>"
        )

    if display.mode != WorkPlanDisplayMode.SHOW_PLAN or not isinstance(display.content, dict):
        return ""

    lines = _format_plan_body(content=display.content, detail_id=display.detail_id, task_status=task_status)

    if task_status == "NEEDS_USER_READ" and display.content.get("plan_status") == "draft":
        lines.extend(
            [
                f"Одобрить и запустить: /run {task_id}",
                f"Отклонить и доработать: /ask {task_id} <feedback>",
            ]
        )

    return "\n".join(lines)
