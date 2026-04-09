Timestamp: 2026-03-17 00:00 UTC

Goal:
- Add Telegram commands for the new “Fridge + Diet + Meal recommendations” scenario.

Reason:
- Provide a dedicated UX in Telegram for listing fridge inventory, adding/removing items, and requesting meal recommendations.

Scope:
- Add `/fridge`, `/fridge_add`, `/fridge_remove`, `/meal` commands that write `events.user_request` with `request.domain="fridge"` and structured `request.fridge_action`.
- Improve DONE notification formatting for fridge domain tasks.

AffectedRepos:
- reminder-bot

AffectedFiles:
- /root/reminder-bot/app/bot/handlers.py
- /root/reminder-bot/app/worker/core_task_notify_worker.py
