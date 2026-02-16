# Security notes (reminder-bot)

Baseline (system-level): `/root/docs/security.md`.

## Secrets

Do not commit secrets (Telegram tokens, DB passwords, etc).

Typical configuration locations (examples, without values):
- `/root/reminder-bot/.env.systemd`

## Logs

- Do not print tokens/DSNs to logs.
- When sharing logs, prefer short tails and redact sensitive values.

## Data boundaries

- `reminder-bot` writes incoming user requests/commands into the shared `events` table (Postgres).
- It does not run LLMs and does not create PRs.

