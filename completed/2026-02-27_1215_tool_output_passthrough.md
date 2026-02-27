Timestamp: 2026-02-27 12:15 UTC
Goal: Prevent Telegram delivery failures for long core task outputs.
Reason: Some core task answers (especially tool outputs) can exceed Telegram message limits and cause permanent send failures.
Scope: Add a conservative truncation guard in Telegram notify worker.
AffectedRepos: reminder-bot
AffectedFiles:
- /root/reminder-bot/app/worker/core_task_notify_worker.py

