from __future__ import annotations


def _icon_for_result(result: str, error_code: str | None = None) -> str:
    if result == "pass":
        return "✅"
    if result == "fail":
        return "❌"
    if result == "error":
        return "⚠"
    if result == "skip" and error_code == "prerequisite_missing":
        return "⏭"
    if result == "skip":
        return "⏭"
    return "•"


def format_review_checks_section(
    *,
    review_iter: int | None,
    summary: dict | None,
    results: list[dict],
) -> str:
    if not results and not summary:
        return ""
    lines: list[str] = []
    iter_label = int(review_iter) if isinstance(review_iter, int) else None
    if iter_label is not None:
        lines.append(f"Review checks (iteration {iter_label}):")
    else:
        lines.append("Review checks:")

    ordered = sorted(
        results,
        key=lambda r: (
            0 if r.get("result") == "fail" else 1,
            str(r.get("check_slug") or ""),
        ),
    )
    for row in ordered:
        if not isinstance(row, dict):
            continue
        name = row.get("check_name") or row.get("check_slug") or "check"
        result = str(row.get("result") or "")
        error_code = row.get("error_code") if isinstance(row.get("error_code"), str) else None
        icon = _icon_for_result(result, error_code=error_code)
        detail = str(row.get("summary") or "").strip()
        if result == "fail" and isinstance(row.get("findings"), list) and row["findings"]:
            f0 = row["findings"][0]
            if isinstance(f0, dict) and isinstance(f0.get("message"), str) and f0["message"].strip():
                detail = f0["message"].strip()
        if error_code == "prerequisite_missing" and detail:
            detail = f"prerequisite_missing: {detail}"
        lines.append(f"  {icon} {name} — {result.title()} — {detail}".rstrip(" —"))

    if isinstance(summary, dict):
        passed = summary.get("checks_passed")
        failed = summary.get("checks_failed")
        total = summary.get("checks_total")
        if isinstance(total, int) and total > 0:
            lines.append("")
            lines.append(f"Policy: {passed}/{total} passed, {failed} failed")
    return "\n".join(lines)


def format_review_checks_notify_summary(*, summary: dict | None) -> str:
    if not isinstance(summary, dict):
        return ""
    aggregate = summary.get("aggregate")
    if aggregate == "checks_passed":
        return ""
    failed = summary.get("checks_failed")
    total = summary.get("checks_total")
    if isinstance(failed, int) and failed > 0:
        return f"Review checks: {failed} failed of {total}."
    if isinstance(aggregate, str) and aggregate:
        return f"Review checks: {aggregate.replace('_', ' ')}."
    return ""
