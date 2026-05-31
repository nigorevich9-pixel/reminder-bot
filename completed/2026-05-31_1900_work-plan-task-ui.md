Timestamp: 2026-05-31 19:00 UTC

Goal: Implement Patch D — reminder-bot work plan UI in `/task <id>`.

Reason: After Patch A/B/C core stores append-only work_plan snapshots and work item progress, but Telegram UI showed only task status and LLM answer; CEO needed visibility into plan/items and NEEDS_USER_READ approve flow.

Scope:
- Read-only display of latest work_plan snapshot in `/task` (draft/approved/rejected-replan).
- Latest-row resolution (rejected blocks older approved/draft); work_items statuses + in_progress highlight.
- NEEDS_USER_READ CTA for `/run` and `/ask`; max 10 items with ellipsis.
- Unit + repo tests, docs, `./check.sh`.

AffectedRepos:
- `/root/reminder-bot`
- `/root/core-orchestrator` (docs only: SCENARIOS §6, STATUS)

AffectedFiles:
- `/root/reminder-bot/app/utils/work_plan_display.py`
- `/root/reminder-bot/app/repositories/core_tasks_repository.py`
- `/root/reminder-bot/app/bot/handlers.py`
- `/root/reminder-bot/tests/test_work_plan_display.py`
- `/root/reminder-bot/tests/test_core_events_and_notify_worker.py`
- `/root/reminder-bot/PROJECT.md`
- `/root/reminder-bot/STATUS.md`
- `/root/reminder-bot/TESTS.md`
- `/root/core-orchestrator/SCENARIOS.md`
- `/root/core-orchestrator/STATUS.md`
