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

test_login_bootstrap_uses_private_temp_files() {
  if grep -n '/tmp/bastion-login-' "${ROOT_DIR}/runtime/internal-bin/bastion-login-bootstrap"; then
    printf 'Fixed /tmp login bootstrap path found\n' >&2
    exit 1
  fi
}

test_daemon_connection_handling_is_bounded() {
  if ! grep -q 'MAX_CONCURRENT_CONNECTIONS' "${ROOT_DIR}/runtime/lib/python/bastion_bootstrapd.py"; then
    printf 'Daemon connection limit constant not found\n' >&2
    exit 1
  fi

  if grep -n 'target=self\.handle_connection,' "${ROOT_DIR}/runtime/lib/python/bastion_bootstrapd.py"; then
    printf 'Unbounded daemon connection handler thread found\n' >&2
    exit 1
  fi
}

test_required_option_values_fail_cleanly() {
  local tmp

  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  if (require_arg "--policy" "") 2> "$tmp"; then
    printf 'require_arg accepted an empty option value\n' >&2
    exit 1
  fi

  grep -q 'Missing value for --policy' "$tmp" || {
    printf 'require_arg did not emit controlled missing-value error\n' >&2
    exit 1
  }

  if (require_arg "--policy" "--other") 2> "$tmp"; then
    printf 'require_arg accepted another option as a value\n' >&2
    exit 1
  fi
}

source "${ROOT_DIR}/runtime/lib/audit.sh"
source "${ROOT_DIR}/runtime/lib/common.sh"

test_policy_user_lookups_are_indexed
test_audit_event_json_escapes_details
test_login_bootstrap_uses_private_temp_files
test_daemon_connection_handling_is_bounded
test_required_option_values_fail_cleanly

printf 'Policy lookup and audit JSON safety check passed\n'
