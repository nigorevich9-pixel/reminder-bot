# Ops / runbook (reminder-bot)

System-level ops map lives in `/root/server-docs/docs/ops.md`.

## Local run

- Bot: `python -m app.bot.main`
- Worker: `python -m app.worker.runner`

## Migrations

Alembic: `alembic/`.

## Services (systemd on VDS)

- `reminder-bot.service`
- `reminder-worker.service`
- `jira-worker.service` (deprecated / optional; see `PROJECT.md`)

## Logs

- systemd logs:
  - `journalctl -u reminder-bot.service -n 200 --no-pager`
  - `journalctl -u reminder-worker.service -n 200 --no-pager`
  - `systemctl status reminder-bot.service`

## Typical symptoms → where to look

- `events` появляются, но `tasks` не создаются:
  - это не проблема `reminder-bot` (он только пишет `events`), проверить `core-event-worker.service`
- Пользователь не получает финальный ответ:
  - проверить `reminder-worker.service`
  - проверить, что в БД есть `tasks.status IN ('DONE','FAILED','STOPPED_BY_USER')` и нужные артефакты (`task_details(kind=llm_result)` / `codegen_result`)
  - проверить `task_details(kind=tg_delivery)` по `message_kind='final'` (последний attempt: `status/retryable/next_attempt_at/error`)
- Не приходит “нужно уточнение”:
  - проверить `tasks.status='WAITING_USER'`
  - проверить `task_details(kind=waiting_user_reason)` (если clarify пришёл от machine review)

## Smoke checks

- Repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- End-to-end sanity across repos: `cd /root && ./test_all.sh`

