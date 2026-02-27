Timestamp: 2026-02-27 13:01 UTC
Goal: Pretty-print JSON answers in Telegram notifications and send oversized JSON as a file.
Reason: Compact JSON is hard to read in Telegram and may exceed message limits; pretty formatting and document delivery improve UX.
Scope: reminder-worker core task notifications (final/needs_review).
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py
- tests/test_core_events_and_notify_worker.py

