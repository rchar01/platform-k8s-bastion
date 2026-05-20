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

test_policy_identity_validation_is_wired() {
  grep -q 'POLICY_LINUX_NAME_PATTERN' "${ROOT_DIR}/runtime/lib/policy.sh" || {
    printf 'Policy Linux identity validation pattern not found\n' >&2
    exit 1
  }

  for script in \
    "${ROOT_DIR}/runtime/sbin/bastion-bootstrap-user-groups" \
    "${ROOT_DIR}/runtime/sbin/bastion-bootstrap-admin-kubeconfig" \
    "${ROOT_DIR}/runtime/sbin/bastion-disable-user"; do
    grep -q 'policy_validate_identity_names\|policy_read' "$script" || {
      printf 'Policy identity validation not wired in %s\n' "$script" >&2
      exit 1
    }
  done
}

test_csr_names_are_dns1123_with_hash() {
  local name long_name

  name="$(dns1123_name_with_hash 'User.Name_With@Invalid/Chars' 'Renew_ABC')"
  [[ "$name" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || {
    printf 'CSR name is not DNS-1123 compatible: %s\n' "$name" >&2
    exit 1
  }
  [[ "$name" == user-name-with-invalid-chars-renew-abc-* ]] || {
    printf 'CSR name does not preserve sanitized user/suffix prefix: %s\n' "$name" >&2
    exit 1
  }
  [[ "$name" =~ -[0-9a-f]{10}$ ]] || {
    printf 'CSR name does not include expected hash suffix: %s\n' "$name" >&2
    exit 1
  }

  long_name="$(dns1123_name_with_hash "$(printf 'a%.0s' {1..300})" 'renew')"
  ((${#long_name} <= 253)) || {
    printf 'CSR name exceeds Kubernetes name length: %s\n' "${#long_name}" >&2
    exit 1
  }
}

test_audit_event_json_escapes_details() {
  local tmp line

  need_cmd jq
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  audit_log_path() { printf '%s\n' "$tmp"; }

  SUDO_USER=$'actor"name\\with\nnewline' \
    PROGRAM_NAME=$'audit-json-test"program' \
    audit_event $'quote"action\\name' $'ok"outcome' $'details with "quotes"\\slashes\nand newline'

  IFS= read -r line < "$tmp"

  jq -e \
    --arg program $'audit-json-test"program' \
    --arg action $'quote"action\\name' \
    --arg outcome $'ok"outcome' \
    --arg actor $'actor"name\\with\nnewline' \
    --arg details $'details with "quotes"\\slashes\nand newline' \
    '.program == $program and .action == $action and .outcome == $outcome and .actor == $actor and .details == $details' <<< "$line" > /dev/null
}

test_root_log_path_overrides_are_ignored() {
  grep -q 'EUID.*-eq 0' "${ROOT_DIR}/runtime/lib/audit.sh" || {
    printf 'Audit log path does not ignore root environment overrides\n' >&2
    exit 1
  }
  grep -q 'EUID.*-eq 0' "${ROOT_DIR}/runtime/lib/log.sh" || {
    printf 'General log path does not ignore root environment overrides\n' >&2
    exit 1
  }
}

test_disable_user_uses_safe_kubeconfig_removal() {
  local script

  script="${ROOT_DIR}/runtime/sbin/bastion-disable-user"
  if grep -n 'run_cmd mv "\$path" "\$backup"' "$script"; then
    printf 'bastion-disable-user still root-renames user-controlled kubeconfig paths\n' >&2
    exit 1
  fi
  grep -q 'bastion_kubeconfig_writer.py' "$script" || {
    printf 'bastion-disable-user does not use the safe kubeconfig writer\n' >&2
    exit 1
  }
  grep -q -- '--remove bootstrap --remove config' "$script" || {
    printf 'bastion-disable-user does not remove both kubeconfig files safely\n' >&2
    exit 1
  }
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

test_csr_cleanup_selects_approved_csrs_only() {
  grep -q 'any(.status.conditions\[\]?; .type == "Approved")' "${ROOT_DIR}/runtime/sbin/bastion-csr-cleanup" || {
    printf 'CSR cleanup does not restrict deletion to approved CSRs\n' >&2
    exit 1
  }
}

test_kubeconfig_expiry_help_and_validation() {
  local script tmp

  script="${ROOT_DIR}/runtime/bin/bastion-kubeconfig-expiry"
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN

  "$script" --help > "$tmp"
  grep -q 'bastion-kubeconfig-expiry \[FILE|DIR\]' "$tmp" || {
    printf 'bastion-kubeconfig-expiry help output is missing expected usage\n' >&2
    exit 1
  }

  if WARN_DAYS=abc "$script" --help > /dev/null; then
    :
  else
    printf 'bastion-kubeconfig-expiry --help should not validate WARN_DAYS\n' >&2
    exit 1
  fi

  if WARN_DAYS=abc "$script" /nonexistent > "$tmp" 2>&1; then
    printf 'bastion-kubeconfig-expiry accepted invalid WARN_DAYS\n' >&2
    exit 1
  fi
  grep -q 'WARN_DAYS must be integer' "$tmp" || {
    printf 'bastion-kubeconfig-expiry did not emit controlled WARN_DAYS error\n' >&2
    exit 1
  }
}

source "${ROOT_DIR}/runtime/lib/audit.sh"
source "${ROOT_DIR}/runtime/lib/common.sh"

test_policy_user_lookups_are_indexed
test_policy_identity_validation_is_wired
test_csr_names_are_dns1123_with_hash
test_audit_event_json_escapes_details
test_root_log_path_overrides_are_ignored
test_disable_user_uses_safe_kubeconfig_removal
test_login_bootstrap_uses_private_temp_files
test_daemon_connection_handling_is_bounded
test_required_option_values_fail_cleanly
test_csr_cleanup_selects_approved_csrs_only
test_kubeconfig_expiry_help_and_validation

printf 'Policy lookup and audit JSON safety check passed\n'
