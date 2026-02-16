---
name: Enable codegen_result Telegram notifications
overview: Connect existing `codegen_result` notification handler into the main `reminder-worker` loop so users get one-shot Telegram updates (PR URL + tests status) per roadmap Stage 2.5.
todos:
  - id: wire-codegen-into-worker-loop
    content: Update `reminder-bot/app/worker/runner.py` to import and call `process_core_codegen_notifications()` in the main `run_loop()`.
    status: completed
  - id: update-docs
    content: Update `reminder-bot/STATUS.md` and `reminder-bot/PROJECT.md` to reflect that codegen notifications are now enabled.
    status: completed
  - id: run-tests
    content: Run `reminder-bot` checks (`./check.sh`) to verify `test_codegen_result_is_notified_once` and the rest of the suite pass.
    status: completed
  - id: restart-worker-unit
    content: Restart `reminder-worker.service` on the VDS and spot-check logs for codegen notification sending.
    status: in_progress
isProject: false
---

## Goal

Enable Telegram notifications for `task_details.kind='codegen_result'` by wiring the already-implemented handler into `reminder-worker`’s main loop.

## What already exists (no new logic needed)

- `reminder-bot` already implements one-shot codegen notifications:
  - Processor: `process_core_codegen_notifications()` in `[/root/reminder-bot/app/worker/core_task_notify_worker.py](/root/reminder-bot/app/worker/core_task_notify_worker.py)`
  - Queue query + idempotency marker (`tg_codegen_notified`): `CoreTasksRepository.pop_one_task_for_codegen_notify()` in `[/root/reminder-bot/app/repositories/core_tasks_repository.py](/root/reminder-bot/app/repositories/core_tasks_repository.py)`
- Test already exists and passes when the processor is invoked:
  - `test_codegen_result_is_notified_once` in `[/root/reminder-bot/tests/test_core_events_and_notify_worker.py](/root/reminder-bot/tests/test_core_events_and_notify_worker.py)`
- Current gap: `reminder-worker` loop does not call the codegen processor (see `[/root/reminder-bot/app/worker/runner.py](/root/reminder-bot/app/worker/runner.py)`).

## Implementation (recommended: wire into main loop)

- Edit `[/root/reminder-bot/app/worker/runner.py](/root/reminder-bot/app/worker/runner.py)`
  - Add import of `process_core_codegen_notifications` alongside the other core notification processors.
  - In `run_loop()`, call `process_core_codegen_notifications(session, bot, limit=20)` after existing core notification calls.
  - Log the count similarly to the other processors.

This is a minimal change and matches the roadmap’s suggested option “подключить обработку в основном worker loop”.

## Docs consistency

- Update `[/root/reminder-bot/STATUS.md](/root/reminder-bot/STATUS.md)` and `[/root/reminder-bot/PROJECT.md](/root/reminder-bot/PROJECT.md)` to remove/adjust the note that codegen notifications are implemented but not connected.

## Verification

- Run reminder-bot checks:
  - `cd /root/reminder-bot && DATABASE_URL=postgresql+asyncpg://..._test@localhost:5432/... && ./check.sh`
  - Ensure `tests/test_core_events_and_notify_worker.py::test_codegen_result_is_notified_once` passes.

## Deploy / ops

- On the VDS, restart the worker unit so the new loop runs:
  - `sudo systemctl restart reminder-worker`
  - Confirm logs show “Sent X core codegen notifications” when a new `codegen_result` arrives.

