#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

assert_contains() {
  local file="$1"
  local pattern="$2"
  local message="$3"

  if ! grep -qE "$pattern" "$file"; then
    printf '%s\n' "$message" >&2
    exit 1
  fi
}

assert_not_contains() {
  local file="$1"
  local pattern="$2"
  local message="$3"

  if grep -nE "$pattern" "$file"; then
    printf '%s\n' "$message" >&2
    exit 1
  fi
}

test_root_token_state_permissions() {
  local issue_script

  issue_script="${ROOT_DIR}/runtime/sbin/bastion-bootstrap-token-issue"
  assert_contains "$issue_script" 'install -m 0700 -d "\$BOOTSTRAP_TOKEN_STATE_DIR"' \
    'Bootstrap token state directory is not created with mode 0700'
  assert_contains "$issue_script" 'chmod 0600 "\$tmp"' \
    'Bootstrap token state file is not chmodded to mode 0600 before publish'
  assert_contains "$issue_script" 'mv -T "\$tmp" "\$dst"' \
    'Bootstrap token state file is not atomically published with mv -T'
}

test_daemon_token_cache_permissions() {
  local daemon

  daemon="${ROOT_DIR}/runtime/lib/python/bastion_bootstrapd.py"
  assert_contains "$daemon" 'os\.chmod\(RUNTIME_TOKENS_DIR, 0o700\)' \
    'Daemon token cache directory is not chmodded to mode 0700'
  assert_contains "$daemon" 'def write_json_file\(path: Path, data: dict\[str, Any\], mode: int = 0o600\)' \
    'Daemon JSON writer does not default cache files to mode 0600'
  assert_contains "$daemon" '"tokenIdRedacted": True' \
    'Daemon logs do not mark token IDs as redacted'
}

test_token_ids_are_redacted_from_audit_and_state() {
  assert_not_contains "${ROOT_DIR}/runtime/sbin/bastion-bootstrap-token-issue" 'audit_event .*token_id=\$\{?token_id' \
    'Token issue audit event includes a raw token ID'
  assert_not_contains "${ROOT_DIR}/runtime/sbin/bastion-bootstrap-token-revoke" 'audit_event .*token_id=\$\{?TOKEN_ID' \
    'Token revoke audit event includes a raw token ID'
  assert_not_contains "${ROOT_DIR}/runtime/sbin/bastion-bootstrap-kubeconfig" 'audit_event .*token_id=\$\{?token_id' \
    'Bootstrap kubeconfig audit event includes a raw token ID'
  assert_not_contains "${ROOT_DIR}/runtime/internal-bin/bastion-login-bootstrap" 'audit_event .*token_id=\$\{?token_id' \
    'Login bootstrap audit event includes a raw token ID'
  assert_not_contains "${ROOT_DIR}/runtime/internal-bin/bastion-login-bootstrap" 'lastTokenId: .*\$token' \
    'Login bootstrap state stores a raw token ID'
  assert_not_contains "${ROOT_DIR}/runtime/sbin/bastion-csr-approver" 'audit_event .*requester=\$\{?requester\}?( |"|$)' \
    'CSR approver audit event includes an unredacted bootstrap requester token'
}

test_root_token_state_permissions
test_daemon_token_cache_permissions
test_token_ids_are_redacted_from_audit_and_state

printf 'Token cache safety check passed\n'
