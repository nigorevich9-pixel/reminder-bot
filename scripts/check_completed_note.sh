#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

_base_ref() {
  if git show-ref --verify --quiet "refs/remotes/origin/main"; then
    echo "origin/main"
    return 0
  fi
  if git show-ref --verify --quiet "refs/heads/main"; then
    echo "main"
    return 0
  fi
  if git rev-parse --verify -q "HEAD^" >/dev/null 2>&1; then
    echo "HEAD^"
    return 0
  fi
  return 1
}

base_ref="$(_base_ref || true)"
if [[ -z "${base_ref}" ]]; then
  exit 0
fi

changed="$(git diff --name-only "${base_ref}...HEAD" --)"
non_doc="$(printf '%s\n' "${changed}" | grep -vE '^docs/' || true)"

if [[ -z "${non_doc}" ]]; then
  exit 0
fi

note_paths="$(printf '%s\n' "${changed}" | grep -E '^completed/[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{4}_.+\.md$' || true)"
if [[ -z "${note_paths}" ]]; then
  n="$(printf '%s\n' "${non_doc}" | grep -c . || true)"
  echo "ERROR: Code changes detected (${n} files). Add completed/YYYY-MM-DD_HHMM_slug.md (UTC) with Timestamp/Goal/Reason/Scope." >&2
  exit 2
fi

ok="0"
while IFS= read -r p; do
  [[ -z "${p}" ]] && continue
  if [[ -f "${p}" ]]; then
    if grep -qE '^Timestamp:' "${p}" \
      && grep -qE '^Goal:' "${p}" \
      && grep -qE '^Reason:' "${p}" \
      && grep -qE '^Scope:' "${p}"; then
      ok="1"
      break
    fi
  fi
done <<<"${note_paths}"

if [[ "${ok}" != "1" ]]; then
  echo "ERROR: completed note is missing required fields: Timestamp/Goal/Reason/Scope." >&2
  echo "Found completed files in diff:" >&2
  printf '%s\n' "${note_paths}" >&2
  exit 2
fi

