Timestamp: 2026-03-04 18:47 UTC
Goal: Fix read_file paging deliveries so /ask next|all uses the newly written chunks.
Reason: reminder-bot repository helpers filtered llm_result by purpose and ignored `read_file_paging_next`/`read_file_paging_all`, causing TG to resend the original truncated chunk.
Scope: Expand allowed llm_result purposes in `CoreTasksRepository.get_latest_llm_result/get_latest_llm_answer` and add regression tests for WAITING_USER paging and DONE paging-all delivery.
AffectedRepos: reminder-bot
AffectedFiles:
- app/repositories/core_tasks_repository.py
- tests/test_core_events_and_notify_worker.py

