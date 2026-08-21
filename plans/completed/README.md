# completed/

This directory contains **change notes** for a “Specification-First” workflow.

## Rule

If a PR contains **any changes outside `docs/**`**, it must also include a new note file:

- `completed/YYYY-MM-DD_HHMM_<slug>.md`
- timestamp is **UTC**
- required fields: `Timestamp`, `Goal`, `Reason`, `Scope`, `AffectedRepos`
- recommended: `AffectedFiles` (explicit file paths)

## Template

```markdown
# <short title>

Timestamp: 2026-02-17 18:30 UTC
Goal: <what we want to achieve>
Reason: <why we are changing this now>
Scope: <what files/modules are affected>
AffectedRepos: <one or more repos/dirs, e.g. reminder-bot, core-orchestrator>
AffectedFiles: <explicit file paths (optional but preferred)>

## Notes

- <optional>
```

