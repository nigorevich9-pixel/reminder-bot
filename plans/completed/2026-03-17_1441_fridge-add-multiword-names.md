Timestamp: 2026-03-17 14:41 UTC

Goal:
- Fix `/fridge_add` and `/fridge_remove` parsing for multi-word product names.

Reason:
- The parser treated the product name as a single token, shifting `qty`/`unit` and causing downstream fridge scenario errors for most real inputs.

Scope:
- Update `_parse_fridge_item_line()` to parse `<name...> <qty> <unit>` with trailing `key=value` attributes.
- Adjust help text examples to show multi-word names.

AffectedRepos:
- reminder-bot

AffectedFiles:
- /root/reminder-bot/app/bot/handlers.py
