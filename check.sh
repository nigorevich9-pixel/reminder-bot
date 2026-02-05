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

