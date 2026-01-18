# Reminder Service — Status

## Текущее состояние
- Бот и воркер работают на VDS (systemd)
- Jira polling включен, рабочее окно 09:00–19:00, утренний catch-up 19:00→09:00
- Репозиторий на GitHub: `nigorevich9-pixel/reminder-bot`

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
