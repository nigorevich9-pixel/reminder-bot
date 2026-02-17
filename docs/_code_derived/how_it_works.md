# reminder-bot — как работает сейчас

## Telegram bot

Entry: `app/bot/main.py` (aiogram polling).

Роуты/хендлеры:
- `app/bot/handlers.py` — core UI и напоминания
- `app/bot/jira_handlers.py` — Jira UI (если модуль доступен)

## Shared inbox events

Запись события:
- `app/repositories/core_tasks_repository.py::insert_event(...)`

Payload формируют хендлеры:
- `event_type=user_request` — новый запрос
- `event_type=user_command` — управление task

## Workers

- `app/worker/runner.py` — цикл: отправка due reminders + уведомления по core tasks
- `app/worker/core_task_notify_worker.py` — выборка задач, формирование сообщений
- `app/worker/jira_worker.py` — Jira polling/обработка (если включено)

