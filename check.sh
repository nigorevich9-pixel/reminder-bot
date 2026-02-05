#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${repo_root}"

DATABASE_URL="${DATABASE_URL:-}"
if [[ -z "${DATABASE_URL}" ]]; then
  echo "ERROR: DATABASE_URL is required (must point to a *_test database)." >&2
  exit 2
fi

if [[ "${DATABASE_URL}" != *"_test"* ]]; then
  echo "ERROR: DATABASE_URL must point to a *_test database. Got: ${DATABASE_URL}" >&2
  exit 2
fi

if [[ "${DATABASE_URL}" != *"@localhost"* && "${DATABASE_URL}" != *"@127.0.0.1"* ]]; then
  echo "ERROR: DATABASE_URL host must be localhost/127.0.0.1 for safety. Got: ${DATABASE_URL}" >&2
  exit 2
fi

echo "[db] reset test DB state"
python3 - <<'PY'
import asyncio
import os

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


async def _reset_db() -> None:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            try:
                await conn.execute(sa.text("DROP SCHEMA public CASCADE"))
                await conn.execute(sa.text("CREATE SCHEMA public"))
                print("[db] reset: dropped+created public schema")
                return
            except Exception as exc:
                print(f"[db] reset: drop schema failed, fallback to DROP TABLE/SEQUENCE ({exc})")

        async with engine.connect() as conn:
            res = await conn.execute(
                sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
            )
            tables = [r[0] for r in res.fetchall()]
            for t in tables:
                await conn.execute(sa.text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))

            res = await conn.execute(
                sa.text("SELECT sequencename FROM pg_sequences WHERE schemaname = 'public' ORDER BY sequencename")
            )
            seqs = [r[0] for r in res.fetchall()]
            for s in seqs:
                await conn.execute(sa.text(f'DROP SEQUENCE IF EXISTS "{s}" CASCADE'))

            print(f"[db] reset: dropped {len(tables)} tables and {len(seqs)} sequences")
    finally:
        await engine.dispose()


asyncio.run(_reset_db())
PY

RUN_MIGRATIONS="${RUN_MIGRATIONS:-1}"

if [[ "${RUN_MIGRATIONS}" == "1" ]]; then
  echo "[reminder-bot] alembic upgrade head"
  python3 -m alembic upgrade head

  # Integration tests require core tables too (tasks/llm_requests/etc).
  echo "[core-orchestrator] alembic upgrade head"
  (
    cd "${repo_root}/../core-orchestrator"
    python3 -m alembic upgrade head
  )
fi

echo "[reminder-bot] unit/functional tests"
python3 -m unittest discover -s tests -p "test_*.py"

