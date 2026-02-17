# reminder-bot — конфиг

См. `app/config/settings.py`.

Ключевые ENV:
- `TG_TOKEN` — токен бота (обязателен)
- `DATABASE_URL` — Postgres
- `JIRA_*` — параметры Jira (если включено)

Важно: bot использует async SQLAlchemy (`AsyncSessionLocal` в `app/db.py`).

