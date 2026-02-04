# Reminder Service — Status

## Текущее состояние
- Бот и воркер работают на VDS (systemd)
- Jira polling включен, рабочее окно 09:00–19:00, утренний catch-up 19:00→09:00
- Репозиторий на GitHub: `nigorevich9-pixel/reminder-bot`
- `users/reminders/jira_*` в `reminder_db` используются как базовые таблицы; core-оркестратор расширяет БД новыми таблицами (не ломая бота)
- `reminder-bot` также пишет входящие команды/запросы в shared inbox таблицу `events` (для `core-orchestrator`).

## Подключения
- Postgres URL: `postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db`
- Redis URL: `redis://localhost:6379/0`
- Env: `/root/reminder-bot/.env.systemd`

## Сервисы (systemd)
- `/etc/systemd/system/reminder-bot.service`
- `/etc/systemd/system/reminder-worker.service`
- `/etc/systemd/system/jira-worker.service`

## Осталось сделать (общие)
- Персистентные таймзоны пользователей (если понадобится)
- Доп. очистка/архивирование старых уведомлений
- По мере взросления: вынести orchestration-задачи (tasks/events/llm_requests/codegen) в `core-orchestrator` и оставить этот проект как UI+reminders

## Примечание про `events`
- `events` — shared inbox. В ней включены idempotency индексы (`source+external_id`, `payload_hash`).
- `core-orchestrator` читает `events`, создаёт `tasks` и дальше ведёт pipeline через `llm_requests/llm_responses`.
