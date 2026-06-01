# reminder-bot

Telegram bot (UI) + reminders, and UI/notifications for `core-orchestrator` tasks.

Также содержит UI для fridge/meal-домена (`/fridge`, `/fridge_add`, `/fridge_remove`, `/fridge_update`, `/meal` — через `core-orchestrator`).

Docs last reviewed: 2026-06-01.

## Quickstart (dev / smoke)

- Run repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- Or run all repos: `cd /root && ./test_all.sh`

Important: `DATABASE_URL` must point to a `*_test` DB on `localhost`/`127.0.0.1` (guards exist in `app/config/settings.py`).

## Команды бота (полный список)

- `/start` — справка
- `/cancel` — отменить создание (FSM)

**Напоминания:**
- `/list`, `/list7`, `/list14`, `/list30` — уведомления
- `/new`, `/edit`, `/disable <id>`, `/delete <id>`

**Orchestrator UI (`core-orchestrator`):**
- `/core` — создать вопрос/задачу (FSM: kind → text → run_mode)
- `/tasks`, `/task <id>`, `/needs_review`
- `/run <id>`, `/hold <id>`, `/ask <id> <text>`

**Fridge / Meal (домен `fridge` через `core-orchestrator`):**
- `/fridge [--expired]` — инвентаризация холодильника
- `/fridge_add` — добавить продукты
- `/fridge_remove` — убрать продукты
- `/fridge_update` — обновить инвентарь по тексту (LLM)
- `/meal <when> [kcal=N] [want=…] [avoid=…]` — рекомендация блюда (LLM)

**Jira (deprecated):**
- `/jira`, `/jira_test`, `/jira_watch`, `/jira_unwatch`, `/jira_list`, `/jira_check`

## Docs (canonical)

- Project overview: `PROJECT.md` — роли, стек, ownership БД, контракт `events`, полный список команд и сценариев
- Current status: `STATUS.md` — текущее состояние сервисов и воркеров
- Config: `CONFIG.md` — все env-переменные с дефолтами и где используются
- How to run tests: `TESTS.md`
- Ops runbook: `OPS.md`
- Security notes: `SECURITY.md`
- AI notes: `AI.md`

System-level map (how projects connect): `/root/server-docs/docs/README.md`.
