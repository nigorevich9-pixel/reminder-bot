# Config (reminder-bot)

Code config entrypoint: `app/config/settings.py` (frozen `dataclass Settings`, читается из env через `python-dotenv`).

Все переменные имеют дефолты, кроме `TG_TOKEN` (required для запуска бота и `app.ops_alert`).

## Основные

| Env var | Default | Где используется | Назначение |
|---|---|---|---|
| `TG_TOKEN` | — (required) | `app/bot/main.py`, `app/worker/runner.py`, `app/ops_alert.py` | Telegram bot token |
| `DATABASE_URL` | `postgresql+asyncpg://reminder_user:reminder_pass@localhost:5432/reminder_db` | `app/db.py:AsyncSessionLocal` | DSN Postgres (asyncpg). Тесты требуют `*_test` в URL — guard в `settings.py` падает, если запущен pytest и URL не test-БД |
| `REDIS_URL` | `redis://localhost:6379/0` | `app/config/settings.py` (заявлен) | URL Redis. Фактическое использование в коде проверить отдельно — в текущем коде прямого обращения к Redis не видно, может быть задел |
| `TG_API_BASE` | `https://api.telegram.org` | передаётся в `aiogram.Bot(token=..., base_url=...)` (наследуется дефолтом) | Альтернативный Telegram Bot API endpoint (для self-hosted / прокси) |
| `DEFAULT_TIMEZONE` | `Europe/Moscow` | `app/worker/runner.py`, парсинг `cron_expr` | TZ по умолчанию для reminder-полей |
| `WORKER_POLL_SECONDS` | `5` | `app/worker/runner.py:run_loop` | Интервал опроса due-reminders и core-уведомлений |
| `TG_DELIVERY_MAX_ATTEMPTS` | `10` | `app/worker/core_task_notify_worker.py` | Макс. попыток доставки уведомления в TG перед тем как сдаться |
| `TG_DELIVERY_MAX_RETRY_WINDOW_SECONDS` | `86400` (24h) | `app/worker/core_task_notify_worker.py` | Окно (сек), в течение которого делаются retry уведомлений |

## Ops alerting

| Env var | Default | Где используется | Назначение |
|---|---|---|---|
| `OPS_CHAT_ID` | — | `app/ops_alert.py` | Telegram chat_id, куда слать алерты через `python -m app.ops_alert --text '...'` |

## Jira (deprecated, optional)

Включается только если при импорте `app.bot.jira_handlers` доступны зависимости (см. `app.bot.main.HAS_JIRA`).

| Env var | Default | Где используется | Назначение |
|---|---|---|---|
| `JIRA_BASE_URL` | `https://legalbet.atlassian.net` | `app/config/settings.py`, `app/services/jira_service.py` | Базовый URL Jira |
| `JIRA_EMAIL` | None | `app/services/jira_service.py` | Email пользователя Jira |
| `JIRA_API_TOKEN` | None | `app/services/jira_service.py` | API token Jira |
| `JIRA_POLL_SECONDS` | `120` | `app/worker/jira_worker.py` | Интервал опроса Jira |

Рекомендация: оставить пустыми, не запускать `jira-worker.service` (см. `PROJECT.md`, раздел "Jira").

## Где лежит реальный env

- `/root/reminder-bot/.env.systemd` — продакшен env (там же лежат `OPS_CHAT_ID`, `GH_TOKEN` и пр. — последний не используется в `app/`, но фигурирует в `.env.systemd`; проверить, не относится ли к внешним интеграциям)
- `.env` (если есть) — локальный override (не коммитится)

## Notes

- Бот использует async SQLAlchemy (см. `AsyncSessionLocal` в `app/db.py`).
- Тесты pytest требуют, чтобы `DATABASE_URL` оканчивался на `*_test` — иначе `settings.py` бросает `RuntimeError` при импорте (см. `_is_running_tests()`).
