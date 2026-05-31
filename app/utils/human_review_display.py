from __future__ import annotations


def format_needs_review_cta(*, task_id: int, pr_url: str | None = None) -> str:
    lines = [
        "PR ждёт вашего решения. Merge в main не выполняется автоматически.",
        "",
        f"Одобрить результат и закрыть задачу: /run {task_id}",
        f"Отклонить и отправить на доработку: /ask {task_id} <что исправить>",
    ]
    if isinstance(pr_url, str) and pr_url.strip():
        lines.extend(["", f"PR: {pr_url.strip()}"])
    return "\n".join(lines)
