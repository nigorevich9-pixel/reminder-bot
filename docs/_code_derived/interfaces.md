# reminder-bot — интерфейсы

## Telegram commands

Core UI:
- `/core` — создать task (question/task)
- `/run <task_id>`
- `/hold <task_id>`
- `/ask <task_id> <text>`

Напоминания:
- команды зависят от реализации в `handlers.py` (например `/new`, `/list`, ...)

## Postgres

Пишет:
- `events` (shared inbox)
- `users`, `reminders`, `jira_subscriptions` (свои таблицы)

Читает:
- `tasks`, `task_details` (core таблицы)

## Внешние зависимости

- Telegram Bot API (через aiogram)
- (опционально) Jira API

