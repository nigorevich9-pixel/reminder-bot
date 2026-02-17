# Contributing (reminder-bot)

## Checks

- Run this repo checks: `cd /root/reminder-bot && DATABASE_URL=... ./check.sh`
- Run all repos: `cd /root && ./test_all.sh`

Important: `DATABASE_URL` must point to a `*_test` DB on `localhost`/`127.0.0.1`.

## Docs

Project docs standard (system-level): `/root/server-docs/docs/README.md`.

When changing behavior/contracts, update docs together with code:
- `PROJECT.md` / `STATUS.md` / `TESTS.md`
- system-level `/root/server-docs/docs/*` (only if it’s about cross-project behavior)

## Security

Do not commit `.env` files, tokens, keys. See `SECURITY.md`.

