Timestamp: 2026-03-17 15:40 UTC

Goal:
- Add a user-friendly `/fridge_update` command that accepts free-text add/remove instructions.

Reason:
- `/fridge_add` requires structured input and is not convenient for day-to-day use.

Scope:
- Add `/fridge_update` Telegram handler that writes `request.domain="fridge"` with `fridge_action.type="update"` and raw user text for LLM parsing in core.
- Update `/start` help text to include `/fridge_update`.

AffectedRepos:
- reminder-bot

AffectedFiles:
- /root/reminder-bot/app/bot/handlers.py
