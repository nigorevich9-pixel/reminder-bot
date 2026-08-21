Timestamp: 2026-02-25T15:48:00Z
Goal: Prevent DONE Telegram delivery from failing with missing message text.
Reason: Some DONE tasks could produce no formatted message (e.g. empty/shifted question text), causing tg_delivery attempts to fail with "missing chat_id/text" despite chat_id being present.
Scope: reminder-bot core task notify worker (DONE notification formatting) + functional smoke test coverage.
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py
- tests/test_core_events_and_notify_worker.py

