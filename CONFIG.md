# Config (reminder-bot)

Code config entrypoint: `app/config/settings.py`.

Key env vars:
- `TG_TOKEN` — Telegram bot token (required)
- `DATABASE_URL` — Postgres DSN
- `JIRA_*` — Jira integration params (optional / deprecated; see `PROJECT.md`)

Notes:
- The bot uses async SQLAlchemy (see `AsyncSessionLocal` in `app/db.py`).

