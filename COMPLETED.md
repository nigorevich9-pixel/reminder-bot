# Completed Tasks

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
