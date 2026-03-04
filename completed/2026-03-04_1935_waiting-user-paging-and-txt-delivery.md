Timestamp: 2026-03-04 19:35 UTC
Goal: Improve TG delivery for large tool outputs and paging flows (read_file chunks and long text answers).
Reason: deliver_to_user + large outputs can exceed TG message limits; paging flows need clear next/all instructions and file delivery.
Scope: Send answer-only WAITING_USER notifications when appropriate, add a dedicated read_file_paging WAITING_USER message with `/ask <task_id> next|all`, and send long plain-text DONE answers as `.txt` documents; also make completed-note checks work without commits and update tests.
AffectedRepos: reminder-bot
AffectedFiles:
- app/worker/core_task_notify_worker.py
- scripts/check_completed_note.sh
- tests/test_core_events_and_notify_worker.py

