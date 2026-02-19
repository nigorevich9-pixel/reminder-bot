# Align /hold documentation with core behavior

Timestamp: 2026-02-19 00:00 UTC
Goal: Make `/hold` documentation consistent with current core semantics and roadmap.
Reason: Reduce user confusion: Telegram UI/docs implied “pause”, but core currently treats `hold` as terminal stop (`STOPPED_BY_USER`) and cancels queued work.
Scope: Documentation-only updates in reminder-bot docs.
AffectedRepos: reminder-bot, core-orchestrator, server-docs
AffectedFiles:
- /root/reminder-bot/PROJECT.md
- /root/reminder-bot/STATUS.md

## Notes

- Current behavior is documented in `/root/core-orchestrator/EVENTS.md`.
- Planned UX change (pause/resume + separate cancel/stop) is tracked in `/root/server-docs/docs/roadmap.md`.

