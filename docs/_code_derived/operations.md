# reminder-bot — эксплуатация

## Запуск

- Bot: `python -m app.bot.main`
- Worker: `python -m app.worker.runner`

## Миграции

Alembic: `alembic/` (таблицы users/reminders/events + индексы).

## Нотификации core

Worker читает `tasks/task_details` и отправляет:
- финальный ответ по question
- уточняющий вопрос (WAITING_USER)
- ссылку на PR по codegen

