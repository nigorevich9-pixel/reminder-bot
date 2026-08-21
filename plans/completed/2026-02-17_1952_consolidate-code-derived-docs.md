Timestamp: 2026-02-17 19:52 UTC

Goal: Consolidate reminder-bot code-derived docs into canonical project markdown files and remove the `_code_derived` snapshot folder.

Reason: `docs/_code_derived` duplicated project information and was not intended to be a source of truth. Keeping a single set of canonical docs in the repo root reduces drift and broken references.

Scope:
- Added `/root/reminder-bot/CONFIG.md` (key env vars + config entrypoint).
- Updated `/root/reminder-bot/README.md` to list `CONFIG.md` as canonical docs.
- Updated `/root/reminder-bot/OPS.md` with local run commands and Alembic migrations pointer.
- Updated `/root/reminder-bot/STATUS.md` with known issues and additional roadmap items.
- Removed `/root/reminder-bot/docs/_code_derived/`.

