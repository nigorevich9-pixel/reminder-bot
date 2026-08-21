Timestamp: 2026-03-17 14:50 UTC

Goal:
- Normalize `/fridge_add` and `/fridge_remove` item units to canonical `g|ml|piece`.

Reason:
- Diet/fridge logic in core assumes canonical units; free-form units (l/kg/jar/pack/portion) cause invalid quantity/unit errors and make calorie calculations unreliable.

Scope:
- Add unit+quantity normalization in `_parse_fridge_item_line()`:
  - `l -> ml` (×1000), `kg -> g` (×1000), `jar/pack/portion -> piece`, common aliases for g/ml/piece.
- Update `/fridge_add` help text to document canonical units and `kcal_per_100g`.

AffectedRepos:
- reminder-bot

AffectedFiles:
- /root/reminder-bot/app/bot/handlers.py
