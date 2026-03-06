Timestamp: 2026-03-06T14:45:18Z
Goal: Stop Telegram JSON “pretty” mode from collapsing tool results (…).
Reason: Full tool outputs must be preserved end-to-end; if content exceeds Telegram limits it should be delivered as a file, not pruned.
Scope: Disable JSON pruning by default for TG formatting; ensure document delivery uses raw (unmodified) answer bytes.
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py

