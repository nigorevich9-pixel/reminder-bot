# reminder-bot

Telegram bot (UI) + reminders, and UI/notifications for `core-orchestrator` tasks.

## Quickstart (dev / smoke)

- Run repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- Or run all repos: `cd /root && ./test_all.sh`

Important: `DATABASE_URL` must point to a `*_test` DB on `localhost`/`127.0.0.1` (guards exist in scripts).

## Docs (canonical)

- Project overview: `PROJECT.md`
- Current status: `STATUS.md`
- How to run tests: `TESTS.md`
- Ops runbook: `OPS.md`
- Security notes: `SECURITY.md`
- AI notes: `AI.md`

System-level map (how projects connect): `/root/docs/index.md`.

