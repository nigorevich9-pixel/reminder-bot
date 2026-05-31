Timestamp: 2026-05-31 21:00 UTC

Goal: Implement Patch E — reminder-bot UX for human NEEDS_REVIEW gate.

Reason: Core Patch E adds approve/reject via `/run`/`/ask`; Telegram UI needed visible CTA and question reject guard.

Scope:
- `human_review_display.py` CTA helper (explicit close-task / rework wording).
- `/task`, `/needs_review`, notify worker integration.
- `/ask` pre-check for NEEDS_REVIEW + kind=question.
- Unit tests, docs, ./check.sh.

AffectedRepos:
- `/root/reminder-bot`

AffectedFiles:
- `/root/reminder-bot/app/utils/human_review_display.py`
- `/root/reminder-bot/app/bot/handlers.py`
- `/root/reminder-bot/app/worker/core_task_notify_worker.py`
- `/root/reminder-bot/tests/test_human_review_display.py`
- `/root/reminder-bot/PROJECT.md`
- `/root/reminder-bot/STATUS.md`
