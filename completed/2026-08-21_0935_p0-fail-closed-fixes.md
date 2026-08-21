Timestamp: 2026-08-21T09:35:00Z

Goal: BLOCKED Telegram UX from * → BLOCKED transitions.

Reason: Core already writes block_reason; bot must notify with role/detail and /run CTA.

Scope: formatter, selector, dedup, tg_delivery tests without live Telegram.

AffectedRepos: reminder-bot

AffectedFiles:
- app/worker/core_task_notify_worker.py
- app/repositories/core_tasks_repository.py
- app/worker/runner.py
- tests/test_core_events_and_notify_worker.py
- STATUS.md
