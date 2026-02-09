# AI notes (reminder-bot)

## What this project is

`reminder-bot` is Telegram UI + reminder/jira features. It also acts as UI for `core-orchestrator` tasks.

## Source of truth (within this project)

- `/root/reminder-bot/PROJECT.md`
- `/root/reminder-bot/STATUS.md`
- `/root/reminder-bot/TESTS.md`
- `/root/reminder-bot/.cursorrules` (project rules)

## Integration notes

- This project **writes** incoming user requests/commands into the shared `events` table (Postgres).
- It **reads** `tasks` / `task_details` to show statuses and deliver results back to Telegram.

