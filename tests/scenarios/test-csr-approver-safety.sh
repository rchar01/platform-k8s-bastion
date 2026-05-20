#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
APPROVER="${ROOT_DIR}/runtime/sbin/bastion-csr-approver"

need_cmd() {
  command -v "$1" > /dev/null 2>&1 || {
    printf 'Missing command: %s\n' "$1" >&2
    exit 1
  }
}

load_approver_functions() {
  source "$APPROVER"
}

test_subject_parser_accepts_openssl_space_format() {
  local subject cn groups

  subject='subject=CN = alice, O = k8s-dev, O = k8s-ops'
  cn="$(subject_cn <<< "$subject")"
  groups="$(subject_groups <<< "$subject")"

  [[ "$cn" == "alice" ]] || {
    printf 'Expected CN alice, got: %s\n' "$cn" >&2
    exit 1
  }
  [[ "$groups" == $'k8s-dev\nk8s-ops' ]] || {
    printf 'Expected two parsed groups, got: %s\n' "$groups" >&2
    exit 1
  }
}

test_subject_parser_accepts_legacy_slash_format() {
  local subject cn groups

  subject='subject=/CN=bob/O=k8s-dev/O=k8s-ops'
  cn="$(subject_cn <<< "$subject")"
  groups="$(subject_groups <<< "$subject")"

  [[ "$cn" == "bob" ]] || {
    printf 'Expected CN bob, got: %s\n' "$cn" >&2
    exit 1
  }
  [[ "$groups" == $'k8s-dev\nk8s-ops' ]] || {
    printf 'Expected two parsed legacy groups, got: %s\n' "$groups" >&2
    exit 1
  }
}

test_bootstrap_owner_requires_unexpired_cache() {
  local tmp future past owner

  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' RETURN
  BOOTSTRAP_DAEMON_TOKEN_CACHE_DIR="${tmp}/daemon"
  BOOTSTRAP_TOKEN_STATE_DIR="${tmp}/state"
  mkdir -p "$BOOTSTRAP_DAEMON_TOKEN_CACHE_DIR" "$BOOTSTRAP_TOKEN_STATE_DIR"

  future="$(date -u -d '+1 hour' +%Y-%m-%dT%H:%M:%SZ)"
  past="$(date -u -d '-1 hour' +%Y-%m-%dT%H:%M:%SZ)"
  jq -n --arg user alice --arg tokenId live-token --arg expiresAt "$future" \
    '{user: $user, tokenId: $tokenId, expiresAt: $expiresAt}' > "${BOOTSTRAP_DAEMON_TOKEN_CACHE_DIR}/1000.json"
  jq -n --arg user bob --arg tokenId expired-token --arg expiresAt "$past" \
    '{user: $user, tokenId: $tokenId, expiresAt: $expiresAt}' > "${BOOTSTRAP_TOKEN_STATE_DIR}/1001.json"

  owner="$(bootstrap_token_owner_for_requester system:bootstrap:live-token)"
  [[ "$owner" == "alice" ]] || {
    printf 'Expected live token owner alice, got: %s\n' "$owner" >&2
    exit 1
  }

  if bootstrap_token_owner_for_requester system:bootstrap:expired-token > /dev/null; then
    printf 'Expired bootstrap token cache was accepted\n' >&2
    exit 1
  fi
}

need_cmd jq
need_cmd sed
need_cmd date

load_approver_functions
test_subject_parser_accepts_openssl_space_format
test_subject_parser_accepts_legacy_slash_format
test_bootstrap_owner_requires_unexpired_cache

printf 'CSR approver parser and token cache safety check passed\n'
