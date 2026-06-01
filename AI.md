# AI notes (reminder-bot)

## What this project is

`reminder-bot` is:
- Telegram UI + reminders (own feature surface: `/new`, `/edit`, `/list*`, `/disable`, `/delete`)
- UI + notification layer for `core-orchestrator` tasks (writes `events`, reads task state/results, notifies users)
- UI for the `fridge` domain (inventory + meal recommendations) — also through `core-orchestrator` via `events` with `request.domain="fridge"` and `request.fridge_action={...}`


## Source of truth (within this project)

- `/root/reminder-bot/PROJECT.md` — обзор, команды, контракт `events`
- `/root/reminder-bot/STATUS.md` — текущее состояние (systemd, патчи D/E)
- `/root/reminder-bot/TESTS.md` — какие тесты есть
- `/root/reminder-bot/CONFIG.md` — env-переменные
- `/root/reminder-bot/OPS.md` — ops runbook
- `/root/reminder-bot/.cursorrules` — project rules

## Integration notes

- This project **writes** incoming user requests/commands into the shared `events` table (Postgres):
  - `/core`, `/fridge*`, `/meal` → `event_type="user_request"` с `request={kind, text, domain?, fridge_action?, auto_run, project_id, attachments}`
  - `/run`, `/hold`, `/ask` → `event_type="user_command"` с `command={name, task_id, text}`
- It **reads** `tasks` / `task_details` to show statuses and deliver results back to Telegram.
- For fridge/meal requests, `request.domain="fridge"` and `request.fridge_action={"type": "inventory_list"|"add"|"remove"|"update"|"recommend", ...}`.

## Where to look in code (high signal)

- Telegram entrypoint: `app/bot/main.py`
- Commands + FSM flows (reminders + core UI + fridge/meal): `app/bot/handlers.py` (1389 строк — главный файл)
- Jira commands (deprecated, опционально подключаются): `app/bot/jira_handlers.py`
- FSM states: `app/bot/states.py`
- `events` writer + task reading helpers: `app/repositories/core_tasks_repository.py` (`insert_event`, `get_task`, `get_latest_llm_result`, `get_latest_llm_answer`, `get_latest_codegen_job`, `get_recent_work_plan_details`, `list_tasks_for_tg`)
- Reminder delivery worker loop: `app/worker/runner.py` (`process_due_reminders` + 6 core-notification вызовов)
- Core task notification helpers (`WAITING_USER/NEEDS_REVIEW/DONE/FAILED/STOPPED_BY_USER` + codegen notify): `app/worker/core_task_notify_worker.py`
- Jira poller (deprecated): `app/worker/jira_worker.py`
- Work plan rendering for `/task`: `app/utils/work_plan_display.py`
- NEEDS_REVIEW CTA: `app/utils/human_review_display.py`
- CLI ops alerts: `app/ops_alert.py`
- Config: `app/config/settings.py`

## Key behavior to keep in mind

- `/core` sends only `request.kind in {"question","task"}` into `events` (reminders are created via `/new` and stored in reminder tables).
- Fridge/meal commands:
  - `/fridge`, `/fridge_add`, `/fridge_remove` → `request.kind="task"`, `request.domain="fridge"`, `request.fridge_action={...}`, `auto_run=True`
  - `/fridge_update`, `/meal` → `request.kind="question"`, `request.domain="fridge"`, `request.fridge_action={...}`, `auto_run=True` (LLM-driven в core)
- Approval gate is effectively `/run <task_id>` (there is also an "auto-run" mode inside `/core` UI).
- Jira integration exists in the repo, but in the current system roadmap it is considered **deprecated** (do not rely on it as part of end-to-end orchestrator scenarios).
- Writer vs reviewer LLM result filtering: бот игнорирует `llm_result` с `purpose in ('question_review','review_loop')` и доставляет пользователю только writer-ответ (см. `_llm_purpose_filter_sql` в `core_tasks_repository`).
