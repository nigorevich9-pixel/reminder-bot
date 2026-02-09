# AI notes (reminder-bot)

## What this project is

`reminder-bot` is Telegram UI + reminders. It also acts as UI for `core-orchestrator` tasks (writes `events`, reads task state/results, notifies users).


## Source of truth (within this project)

- `/root/reminder-bot/PROJECT.md`
- `/root/reminder-bot/STATUS.md`
- `/root/reminder-bot/TESTS.md`
- `/root/reminder-bot/.cursorrules` (project rules)

## Integration notes

- This project **writes** incoming user requests/commands into the shared `events` table (Postgres).
- It **reads** `tasks` / `task_details` to show statuses and deliver results back to Telegram.

## Where to look in code (high signal)

- Telegram entrypoint: `app/bot/main.py`
- Commands + FSM flows (reminders + core UI): `app/bot/handlers.py`
- `events` writer + task reading helpers: `app/repositories/core_tasks_repository.py`
- Reminder delivery worker loop: `app/worker/runner.py`
- Core task notification helpers (`SEND_TO_USER`, `WAITING_USER`, codegen notify helper): `app/worker/core_task_notify_worker.py`

## Key behavior to keep in mind

- `/core` sends only `request.kind in {"question","task"}` into `events` (reminders are created via `/new` and stored in reminder tables).
- Approval gate is effectively `/run <task_id>` (there is also an “auto-run” mode inside `/core` UI).
- Jira integration exists in the repo, but in the current system roadmap it is considered **deprecated** (do not rely on it as part of end-to-end orchestrator scenarios).
