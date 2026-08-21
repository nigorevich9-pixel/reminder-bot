Timestamp: 2026-02-19 14:15 UTC
Goal: Harden Telegram delivery trace for core task notifications.
Reason: Improve debuggability and reliability: richer delivery payload, retry caps/policy, and correct transition selection semantics.
Scope: reminder-bot delivery layer (selectors + notify worker + tests) and docs sync away from legacy SEND_TO_USER.
AffectedRepos: core-orchestrator, reminder-bot
AffectedFiles:
- app/config/settings.py
- app/repositories/core_tasks_repository.py
- app/worker/core_task_notify_worker.py
- tests/test_core_events_and_notify_worker.py
- PROJECT.md
- TESTS.md
- OPS.md
- AI.md
- COMPLETED.md

