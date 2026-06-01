# Ops / runbook (reminder-bot)

System-level ops map: `/root/server-docs/docs/ops.md`.
System-level snapshot (м.б. устарел — проверять `systemctl`): `/root/server-docs/SERVER_STATE.md`.

## Local run

- Bot: `python -m app.bot.main` (или из `.venv`: `/root/reminder-bot/.venv/bin/python3 -m app.bot.main`)
- Worker: `python -m app.worker.runner`
- Ops alert CLI: `python -m app.ops_alert --text "..." [--unit svc-name]`

## Migrations

Alembic: `alembic/`. Запуск:

```bash
cd /root/reminder-bot && alembic upgrade head
```

## Services (systemd on VDS)

- `reminder-bot.service` — Telegram bot. Entry: `app/bot/main.py`.
- `reminder-worker.service` — reminder delivery + core task notification loop. Entry: `app/worker/runner.py`. Цикл: due-reminders, потом 6 типов core-уведомлений (`waiting_user`, `needs_review`, `codegen`, `done`, `failed`, `stopped`). Sleep `WORKER_POLL_SECONDS` (дефолт 5).
- `jira-worker.service` — Jira poller (deprecated / off по умолчанию).

## Logs

- systemd logs:
  - `journalctl -u reminder-bot.service -n 200 --no-pager`
  - `journalctl -u reminder-worker.service -n 200 --no-pager`
  - `journalctl -u jira-worker.service -n 200 --no-pager`
  - `systemctl status <unit>`
- Если нужно отправить алерт в TG (ops-чат): `python -m app.ops_alert --text "..." --unit <svc>`

## Typical symptoms → where to look

- Бот не отвечает на команды, но воркер уведомлений работает:
  - проверить `systemctl status reminder-bot.service` и `journalctl -u reminder-bot.service -n 50`
  - частая причина — сетевая проблема к `api.telegram.org` (`aiogram.exceptions.TelegramNetworkError: Request timeout error`). Бот auto-restart-ит, но в данный момент не работает
- `events` появляются, но `tasks` не создаются:
  - это не проблема `reminder-bot` (он только пишет `events`), проверить `core-event-worker.service` на VDS
- Пользователь не получает финальный ответ:
  - проверить `reminder-worker.service`
  - проверить, что в БД есть `tasks.status IN ('DONE','FAILED','STOPPED_BY_USER')` и нужные артефакты (`task_details(kind=llm_result)` / `codegen_result`)
  - проверить `task_details(kind=tg_delivery)` по `message_kind='final'` (последний attempt: `status/retryable/next_attempt_at/error`)
- Не приходит "нужно уточнение":
  - проверить `tasks.status='WAITING_USER'`
  - проверить `task_details(kind=waiting_user_reason)` (если clarify пришёл от machine review)
- Fridge/meal запросы уходят, но ответа нет:
  - проверить `core-event-worker.service` и `core-llm-result-worker.service`
  - в `events` проверить `payload->'request'->>'domain'='fridge'`

## Smoke checks

- Repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- End-to-end sanity across repos: `cd /root && ./test_all.sh`
- Вручную: вставить `events` запись → дождаться `tasks` → дождаться `llm_requests(IN_PROGRESS)` → `llm_responses` → финальный статус → уведомление в TG.
