Timestamp: 2026-03-06T15:17:37Z
Goal: Make Telegram file-delivery JSON readable (pretty-printed) without losing content.
Reason: When result is delivered as a document, we can format full JSON with indentation for readability while keeping data intact.
Scope: Format `.json` attachments via parse+indent; fallback to original text if parsing fails.
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py

