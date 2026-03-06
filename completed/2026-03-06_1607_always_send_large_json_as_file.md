Timestamp: 2026-03-06T16:07:00Z
Goal: Always send oversized JSON answers as a Telegram file (no prune).
Reason: Text-size limits caused pruned/partial JSON to be shown in Telegram, confusing tool output consumers. Full JSON should be delivered losslessly via document when it does not fit into a message.
Scope: Telegram delivery formatting for NEEDS_REVIEW and DONE notifications.
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py

