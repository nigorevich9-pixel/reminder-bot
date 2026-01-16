# Reminder Service — Status

## Что уже сделано
- Установлены сервисы: PostgreSQL 14, Redis 6
- База создана: `reminder_db`, пользователь: `reminder_user`
- Виртуальное окружение и зависимости в `/root/reminder-bot/.venv`
- Настроен Alembic и созданы миграции
- Созданы таблицы: `users`, `reminders`, `alembic_version`
- Добавлена базовая структура проекта:
  - `app/config/settings.py`
  - `app/models.py`
  - `app/repositories/*`
  - `app/services/*`
  - `app/bot/*`
  - `app/worker/*`

## Подключения
- Postgres URL:
  - `postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db`
- Redis URL:
  - `redis://localhost:6379/0`

## Что уже сделано дополнительно
- Бот с командами `/start`, `/list`, `/list7`, `/list14`, `/list30`, `/new`, `/cancel`
- FSM создания уведомлений с кнопками:
  - тип уведомления
  - день (сегодня/завтра/другая дата)
  - время (пресеты + фиксированные часы + ввод)
- Валидация дат и времени (форматы с дефисами, точками и пробелами)
- Поддержка cron-расписаний с расширенной подсказкой
- Группировка `/list*` по блокам (сегодня/завтра/через N дней/дата)
- Worker для отправки уведомлений (systemd)
- systemd сервисы для бота и worker
- Мониторинг сервиса (Postgres/Redis) в `monitor.sh`
- Env для сервисов: `/root/reminder-bot/.env.systemd`
- Юниты:
  - `/etc/systemd/system/reminder-bot.service`
  - `/etc/systemd/system/reminder-worker.service`

## Что осталось сделать
- Персистентные таймзоны пользователей (если понадобится)
- Доп. очистка/архивирование старых уведомлений
