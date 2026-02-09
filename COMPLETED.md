# Completed Tasks

Note: Jira-related items below are historical; in the current system roadmap Jira is considered deprecated (see `PROJECT.md`).

## Infrastructure
- Установлены PostgreSQL 14 и Redis 6
- Создана база `reminder_db` и пользователь `reminder_user`
- Настроен Alembic, созданы миграции
- Настроены systemd сервисы для бота и воркеров

## Telegram Bot
- Команды: `/start`, `/list`, `/list7`, `/list14`, `/list30`, `/new`, `/cancel`
- FSM сценарий создания напоминаний с клавиатурами
- Валидация дат и времени
- Поддержка cron-расписаний
- Core orchestration UI:
  - `/core` (создать request kind=question/task)
  - `/tasks`, `/task <id>` (просмотр задач/ответов)
  - `/run <id>`, `/hold <id>`, `/ask <id> <text>` (команды в core)
  - `/needs_review` (список задач в статусе NEEDS_REVIEW + возраст)
  - auto-delivery для `SEND_TO_USER` и one-shot уведомление для `WAITING_USER` (в `reminder-worker`)

## Jira Intake
- Jira API integration (polling)
- Подписки на проект/задачу: `/jira_watch`, `/jira_unwatch`, `/jira_list`
- Проверка подключения: `/jira_test`
- Воркер Jira с рабочим окном 09:00–19:00 и утренним catch-up

## Git
- Инициализирован git
- Репозиторий опубликован на GitHub

## Ecosystem
- Выделен отдельный репозиторий `core-orchestrator` (control plane) с миграциями core-таблиц в `reminder_db`

## Testing / Smoke checks
- Добавлены короткие functional smoke тесты (проверяют `events` + доставку `SEND_TO_USER`/`WAITING_USER` без реального Telegram).
- Добавлен `./check.sh` (проверка этого репозитория одной командой) и `/root/test_all.sh` (проверка всех репо по очереди).
- Миграции сделаны воспроизводимыми для чистой test-БД: `events` создаётся через `CREATE TABLE IF NOT EXISTS` перед добавлением denormalized колонок.
