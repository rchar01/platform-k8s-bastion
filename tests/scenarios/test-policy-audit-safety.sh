#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

need_cmd() {
  command -v "$1" > /dev/null 2>&1 || {
    printf 'Missing command: %s\n' "$1" >&2
    exit 1
  }
}

test_policy_user_lookups_are_indexed() {
  if grep -R -n '\.users\.\${' "${ROOT_DIR}/runtime"; then
    printf 'Unsafe yq user lookup interpolation found\n' >&2
    exit 1
  fi
}

test_audit_event_json_escapes_details() {
  local tmp line

  need_cmd jq
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  PROGRAM_NAME="audit-json-test" \
    BASTION_AUDIT_LOG="$tmp" \
    audit_event 'quote"action' 'ok' $'details with "quotes"\nand newline'

  IFS= read -r line < "$tmp"

  jq -e \
    --arg program "audit-json-test" \
    --arg action 'quote"action' \
    --arg details $'details with "quotes"\nand newline' \
    '.program == $program and .action == $action and .details == $details' <<< "$line" > /dev/null
}

source "${ROOT_DIR}/runtime/lib/audit.sh"

test_policy_user_lookups_are_indexed
test_audit_event_json_escapes_details

printf 'Policy lookup and audit JSON safety check passed\n'
