"""
B-markdown-checks display helpers (reminder-bot PR4).

Pure formatting functions (no DB) that turn `review_checks_summary` +
`review_check_result` rows into Telegram-friendly text.

If no `review_checks_summary` exists for the latest review iteration,
the section is omitted (backward compat: pre-PR3 tasks render unchanged).
"""

from __future__ import annotations

from typing import Iterable


# Symbols used in the section. Mapping follows the spec UX table in
# agent_spike_review_checks.md "UX (reminder-bot)".
_PASS = "\u2705"        # ✅
_FAIL = "\u274C"        # ❌
_SKIP = "\u23ED"        # ⏭
_ERROR = "\u26A0"        # ⚠


def _icon_for(result: str) -> str:
    r = (result or "").lower()
    if r == "pass":
        return _PASS
    if r == "fail":
        return _FAIL
    if r == "skip":
        return _SKIP
    if r == "error":
        return _ERROR
    return _ERROR


def _format_check_line(row: dict) -> str:
    """Format one `review_check_result` row as a single Telegram line."""
    name = (row.get("check_name") or row.get("check_slug") or "").strip() or "?"
    result = str(row.get("result") or "error")
    icon = _icon_for(result)
    summary = (row.get("summary") or "").strip()
    error_code = (row.get("error_code") or "").strip()
    if not summary and error_code:
        summary = error_code
    # Truncate to a single line to keep the section compact.
    summary = summary.splitlines()[0] if summary else ""
    if len(summary) > 80:
        summary = summary[:79] + "\u2026"
    if summary:
        return f"{icon} {name} \u2014 {result.capitalize()} \u2014 {summary}"
    return f"{icon} {name} \u2014 {result.capitalize()}"


def format_review_checks_section(
    *,
    summary: dict | None,
    check_results: Iterable[dict] | None = None,
) -> str:
    """Format the "Review checks" section for `/task` output.

    Returns "" if `summary` is None/empty (section omitted). The summary
    must be a `task_details(kind=review_checks_summary).content` dict.

    `check_results` is the list of `review_check_result` rows for the
    same `review_iter` (optional — when provided, used to render
    per-check Pass/Fail/Skip/Error lines).
    """
    if not isinstance(summary, dict) or not summary:
        return ""

    review_iter = summary.get("review_iter")
    aggregate = str(summary.get("aggregate") or "")
    checks_total = summary.get("checks_total")
    checks_passed = summary.get("checks_passed")
    checks_failed = summary.get("checks_failed")
    checks_error = summary.get("checks_error")
    checks_skipped = summary.get("checks_skipped")
    checks_prereq = summary.get("checks_skipped_due_to_prerequisite")

    lines: list[str] = ["Review checks"]
    if review_iter is not None:
        lines[0] = f"Review checks (iteration {review_iter})"
    lines.append("")

    if check_results:
        # Order: failures first, then errors, then prereq skips, then passes.
        def _sort_key(r: dict) -> int:
            res = str(r.get("result") or "")
            ec = str(r.get("error_code") or "")
            if res == "fail":
                return 0
            if res == "error":
                return 1
            if res == "skip" and ec == "prerequisite_missing":
                return 2
            if res == "skip":
                return 3
            return 4

        for row in sorted(list(check_results), key=_sort_key):
            lines.append(_format_check_line(row))
    else:
        # No per-check rows — render aggregate counters.
        lines.append(
            f"Aggregate: {aggregate} "
            f"(passed={checks_passed or 0}, failed={checks_failed or 0}, "
            f"error={checks_error or 0}, skipped={checks_skipped or 0}, "
            f"prereq_skipped={checks_prereq or 0}, total={checks_total or 0})"
        )

    return "\n".join(lines)


def format_review_checks_notify_summary(
    *,
    summary: dict | None,
    max_chars: int = 500,
) -> str:
    """Compact one-line summary for the `review_needed` notify worker.

    Returns "" if summary is None or aggregate is `checks_passed`
    (success cases don't need extra noise). Truncates to `max_chars`.
    """
    if not isinstance(summary, dict) or not summary:
        return ""
    aggregate = str(summary.get("aggregate") or "")
    if aggregate == "checks_passed":
        return ""
    lines = [
        f"Review checks: {aggregate} "
        f"(passed={summary.get('checks_passed') or 0}, "
        f"failed={summary.get('checks_failed') or 0}, "
        f"error={summary.get('checks_error') or 0})"
    ]
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 1)] + "\u2026"
    return text
