# Ops / runbook (reminder-bot)

System-level ops map lives in `/root/docs/ops_and_observability.md`.

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
  - проверить, что в БД есть `tasks.status='SEND_TO_USER'` и `task_details(kind=llm_result)`
- Не приходит “нужно уточнение”:
  - проверить `tasks.status='WAITING_USER'`
  - проверить `task_details(kind=waiting_user_reason)` (если clarify пришёл от machine review)

## Smoke checks

- Repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- End-to-end sanity across repos: `cd /root && ./test_all.sh`

