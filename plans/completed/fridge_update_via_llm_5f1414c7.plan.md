---
name: Fridge update via LLM
overview: Add a new Telegram command `/fridge_update` that accepts free-text add/remove instructions, has core-orchestrator parse them via LLM against the current inventory, and then applies deterministic lot quantity updates (no auto-creating new foods; clarify when ambiguous).
todos:
  - id: tg-fridge-update-command
    content: Add `/fridge_update` Telegram command to write `events.user_request` with `fridge_action.type=update`.
    status: completed
  - id: core-enqueue-fridge-update
    content: In core event worker, enqueue LLM request `purpose=fridge_update` with structured inventory including lot_id.
    status: completed
  - id: prompt-fridge-update
    content: Add `fridge_update_prompt()` with strict schema + clarify rules.
    status: completed
  - id: llm-result-apply-ops
    content: In llm_result_worker, handle `purpose=fridge_update` final/clarify and apply ops to `fr_lots` + `fr_movements` with idempotency guard.
    status: completed
  - id: tests-fridge-update
    content: Add unit tests for ambiguous vs unambiguous fridge_update flows.
    status: completed
isProject: false
---

> **Audit 2026-08-21:** implemented in code/docs. YAML todos in this file may still say pending (stale). Archived to `plans/completed/`.


## Goal

Enable a user-friendly workflow: user sends one message like “добавь литр молока, убери 2 йогурта”, core uses LLM to convert it into structured operations against existing fridge lots, and then applies them deterministically.

## Constraints (from you)

- **No auto-create on add**: if a referenced food/lot doesn’t exist, LLM must ask to clarify (or instruct using `/fridge_add`).
- **Clarify if multiple lots match**: if there are multiple candidate lots for a requested change, LLM must ask a clarification rather than guessing.

## Implementation outline

- **Telegram UI**
  - Add `/fridge_update` handler in `[/root/reminder-bot/app/bot/handlers.py](/root/reminder-bot/app/bot/handlers.py)`.
    - Accept multiline text after the command.
    - Write an `events.user_request` with `request.domain="fridge"` and `request.fridge_action={"type":"update","text":<user_text>}`.
    - Keep existing `/fridge_add` and `/fridge_remove` for power users.
  - Update `/start` help text to include `/fridge_update` and 1–2 examples.
- **Core: enqueue LLM parse request**
  - Extend fridge domain switch in `[/root/core-orchestrator/core_orchestrator/workers/event_worker.py](/root/core-orchestrator/core_orchestrator/workers/event_worker.py)` to handle `fridge_action.type == "update"`.
  - Build an LLM prompt that includes **structured inventory with lot identifiers** so LLM can reference a specific lot.
    - Add a helper (in `event_worker.py`) to produce JSON-ish inventory list including: `lot_id, food_name, quantity, unit, status, purchased_on, expires_on`.
  - Add a new prompt function `fridge_update_prompt(...)` in `[/root/core-orchestrator/core_orchestrator/llm_prompts.py](/root/core-orchestrator/core_orchestrator/llm_prompts.py)`.
    - Hard rules: do not invent foods; if not found or ambiguous, return `{"type":"clarify",...}`.
    - Output schema (final): `{"type":"final","answer":"...","ops":[{"action":"add|remove","lot_id":123,"amount":1000,"unit":"ml"}, ...]}`.
- **Core: apply the operations**
  - Extend `[/root/core-orchestrator/core_orchestrator/workers/llm_result_worker.py](/root/core-orchestrator/core_orchestrator/workers/llm_result_worker.py)` with a new special-case similar to `fridge_recommendation`:
    - When `purpose == "fridge_update"` and raw kind is `question`:
      - If `clarify`: transition to `WAITING_USER` (standard question flow) and deliver the clarify question.
      - If `final`: validate `ops`, then apply each op deterministically:
        - Update `fr_lots.quantity` by `+amount` or `-amount` with safety checks (no negative).
        - Insert `fr_movements` rows with `reason="adjust"` (and `meta` containing the op + LLM request id).
      - Write a `TaskDetail(kind="fridge_result")` summary (applied ops + any errors) and transition task to `DONE`.
    - Add an idempotency guard (e.g. a `TaskDetail(kind="fridge_update_applied", content={llm_request_id})`) to ensure ops are not applied twice.
- **Tests**
  - Add/extend tests in `[/root/core-orchestrator/tests/test_event_worker_and_llm_result_worker.py](/root/core-orchestrator/tests/test_event_worker_and_llm_result_worker.py)`:
    - Seed a fridge with multiple lots and assert that an ambiguous request leads to `clarify`.
    - Seed a fridge with a unique lot and assert that a `final` response updates quantity and inserts a movement.
- **Change notes + rollout**
  - Add `completed/YYYY-MM-DD_HHMM_*.md` change notes (UTC) in both repos for the feature.
  - Restart `reminder-bot.service` and `core-event-worker.service` after deploy.

## Notes on UX

- `/fridge_update` becomes the default human-friendly command.
- `/fridge_add` remains for explicit entry and for introducing new foods/lots.
- In clarify responses, we’ll guide the user to either:
  - pick a specific lot (by showing lot_id/options), or
  - use `/fridge_add` to create the missing product/lot.

