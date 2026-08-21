Timestamp: 2026-06-02T22:30:00Z
Goal: PR4 reminder-bot UX для B-markdown-checks: format_review_checks_section() для /task display + format_review_checks_notify_summary() для review_needed notify, repository-методы для чтения audit rows, integration в /task handler и core_task_notify_worker.
Reason: После PR1-PR3 backend умеет discover/execute/audit checks. PR4 делает результат видимым пользователю в Telegram: при `/task <id>` — секция "Review checks" с Pass/Fail/Skip/Error per-check; при `review_needed` notify — compact summary (≤500 chars) только когда aggregate ≠ checks_passed. Backward compat: tasks без check audit rows рендерятся как раньше.
Scope:
  added:
    - reminder-bot/app/utils/review_checks_display.py (format_review_checks_section, format_review_checks_notify_summary — pure functions, no DB)
    - reminder-bot/tests/test_review_checks_display.py (16 unit-тестов)
  modified:
    - reminder-bot/app/repositories/core_tasks_repository.py: добавлены get_latest_review_checks_summary() и get_review_check_results_for_iter()
    - reminder-bot/app/bot/handlers.py: task_status_handler теперь подгружает review_checks summary и результаты per-iter, рендерит секцию после work_plan
    - reminder-bot/app/worker/core_task_notify_worker.py: _format_needs_review_message расширен kwarg review_checks_summary; оба call site передают его
  no_changes:
    - reminder-bot/app/bot/main.py, app/bot/middlewares.py, app/bot/states.py
    - reminder-bot/app/worker/tasks.py, app/worker/runner.py
    - DB migrations не требуются (читаем из task_details, kind = TEXT)
backward_compat:
  - Если task_details(kind=review_checks_summary) нет для задачи — секция /task рендерится **как раньше** (no extra block).
  - Если aggregate=checks_passed (или summary=None) — notify **без** extra block (format_review_checks_notify_summary returns "").
  - Existing call site _format_needs_review_message — добавлен только опциональный kwarg review_checks_summary=None; positional args неизменны.
  - 16/16 unit-тестов зелёные.
display_format:
  - Header: "Review checks (iteration N)"
  - Per-check line: "{icon} {name} — {Result} — {summary|first_line}" (icons ✅/❌/⏭/⚠)
  - Order: fail → error → prereq_skip → skip → pass (most actionable first)
  - Summary ≤80 chars per line; multi-line summary → first line only
  - Notify summary ≤500 chars, no icon, plain counters
tests:
  - 16/16 test_review_checks_display.py OK:
    * no_summary → empty
    * iteration_in_header
    * all_pass → no fail/error icons
    * fail_listed_first (ordering)
    * prereq_skip icon + error_code
    * error row warning icon
    * error row with no summary uses error_code
    * no check_results uses aggregate line
    * summary_truncates (single line, ≤80 chars)
    * summary_with_newlines uses first line only
    * fallback_name (slug empty → "?")
    * notify: no_summary → empty
    * notify: passed → empty
    * notify: failed → "Review checks: checks_failed (passed=1, failed=1, error=0)"
    * notify: degraded → renders
    * notify: truncates to max_chars
  - check.sh reminder-bot: pending (DATABASE_URL был, но check_completed_note.sh требует note — будет запущен после создания completed файла).
next_pr: PR5 — E2E scenario в core-orchestrator (test_e2e_scenarios.py), example checks в localProject/.continue/checks/, STATUS.md/ROADMAP.md/server-docs updates, perf measurement.
