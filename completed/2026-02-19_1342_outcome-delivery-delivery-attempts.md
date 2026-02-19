Timestamp: 2026-02-19 13:42 UTC
Goal: Make Telegram notifications transition-driven with retry/backoff delivery trace.
Reason: Decouple pipeline outcome (`tasks.status`) from delivery reliability; allow retries when Telegram is temporarily down; avoid using `SEND_TO_USER` as a queue-status.
Scope: reminder-bot (CoreTasksRepository selectors, core notify worker, tests).
AffectedRepos: core-orchestrator, reminder-bot
AffectedFiles:
- app/repositories/core_tasks_repository.py
- app/worker/core_task_notify_worker.py
- app/worker/runner.py
- tests/test_core_events_and_notify_worker.py

