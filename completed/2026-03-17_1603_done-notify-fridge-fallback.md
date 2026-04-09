Timestamp: 2026-03-17 16:03 UTC
Goal: Ensure DONE tasks always deliver a Telegram notification (including fridge flows).
Reason: Some DONE tasks were not notified in Telegram due to strict llm_result purpose allowlist and/or missing DONE transitions (transition-driven notifier skipped them).
Scope: reminder-bot core task notify worker + repository selection logic.
AffectedRepos: reminder-bot
AffectedFiles:
- /root/reminder-bot/app/repositories/core_tasks_repository.py
- /root/reminder-bot/app/worker/core_task_notify_worker.py

