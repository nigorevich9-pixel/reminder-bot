# Reminder Service — Status

## Текущее состояние
- Бот и воркер работают на VDS (systemd)
- Jira в коде присутствует, но для текущей системы считается **deprecated** (см. `PROJECT.md`). По умолчанию `jira-worker` не запускаем.
- Репозиторий на GitHub: `nigorevich9-pixel/reminder-bot`
- `users/reminders/jira_*` в `reminder_db` используются как базовые таблицы; core-оркестратор расширяет БД новыми таблицами (не ломая бота)
- `reminder-bot` также пишет входящие команды/запросы в shared inbox таблицу `events` (для `core-orchestrator`).
- `reminder-worker` также доставляет уведомления по core-задачам:
  - `SEND_TO_USER` → отправка пользователю (вопрос+ответ) → `DONE`
  - `WAITING_USER` → отправка уточняющего вопроса пользователю (one-shot)
  - `codegen_result` → one-shot уведомление (PR URL + статус тестов) — реализовано в коде воркера, но **пока не подключено** в основном loop `reminder-worker` (см. `app/worker/core_task_notify_worker.py` и `app/worker/runner.py`).

## Подключения
- Postgres URL: `postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db`
- Redis URL: `redis://localhost:6379/0`
- Env: `/root/reminder-bot/.env.systemd`

## Сервисы (systemd)
- `/etc/systemd/system/reminder-bot.service`
- `/etc/systemd/system/reminder-worker.service`
- `/etc/systemd/system/jira-worker.service` (deprecated / optional)

## Проверки / тесты (smoke)
- Локальная проверка репозитория: `./check.sh`
- Сквозная проверка всех репо: `/root/test_all.sh`
- Требование безопасности: `DATABASE_URL` должен указывать на test-БД (например `reminder_db_test`) и host `localhost`/`127.0.0.1` (guard включён в скриптах).
- Functional smoke покрывают:
  - запись событий в `events` (включая denormalized поля)
  - доставку задач `SEND_TO_USER`/`WAITING_USER` через stub-бот и корректные transitions

## Осталось сделать (общие)
- Персистентные таймзоны пользователей (если понадобится)
- Доп. очистка/архивирование старых уведомлений
- По мере взросления: вынести orchestration-задачи (tasks/events/llm_requests/codegen) в `core-orchestrator` и оставить этот проект как UI+reminders
- Подключить уведомления по `codegen_result` (либо в `reminder-worker`, либо выделенным отдельным worker unit), если этот UX нужен в Telegram.

## Примечание про `events`
- `events` — shared inbox. В ней включены idempotency индексы (`source+external_id`, `payload_hash`).
- `core-orchestrator` читает `events`, создаёт `tasks` и дальше ведёт pipeline через `llm_requests/llm_responses`.
