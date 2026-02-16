## Plans (PR context)

This folder stores task plans that explain **why** a PR was made.

### File naming

- Prefer including the PR number in the filename:
  - `pr<PRNUM>_<slug>_<planId>.plan.md`
- `planId` is a short unique suffix like `9c2cfe4c` (already present in historical plan filenames).

### Front matter (YAML) fields

Historical plans already include fields like `name`, `overview`, `todos`, etc. For PR linkage we add:

- `repo`: `reminder-bot`
- `pr_number`: integer
- `pr_url`: string
- `matched_by`: `content_paths|filename_keywords|time_window|title_similarity|manual_override`
- `match_confidence`: `high|medium|low`
- `source_plan_path`: absolute path to the original plan (usually under `/root/.cursor/plans/`)
- `source_mtime`: ISO-8601 timestamp (UTC) of the source plan file mtime

### Notes

- Not every PR has a plan (some PRs were created directly). That is OK.
- Ambiguous matches should be left out (only reported), not auto-migrated.
