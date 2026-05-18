#!/usr/bin/env bash

bastion_state_dir() {
  printf '%s\n' "${HOME}/.cache/bastion-bootstrap"
}

bastion_state_file() {
  printf '%s/state.json\n' "$(bastion_state_dir)"
}

bastion_lock_file() {
  printf '%s/lock\n' "$(bastion_state_dir)"
}

bastion_state_init() {
  install -d -m 0700 "$(bastion_state_dir)"
}

bastion_lock_acquire() {
  local timeout_seconds="${1:-15}"
  bastion_state_init

  exec {BASTION_LOCK_FD}> "$(bastion_lock_file)"
  flock -w "$timeout_seconds" "$BASTION_LOCK_FD"
}

bastion_lock_release() {
  if [[ -n "${BASTION_LOCK_FD:-}" ]]; then
    flock -u "$BASTION_LOCK_FD" || true
    eval "exec ${BASTION_LOCK_FD}>&-"
    unset BASTION_LOCK_FD
  fi
}

bastion_state_read_json() {
  local f
  f="$(bastion_state_file)"

  if [[ -s "$f" ]]; then
    cat "$f"
  else
    jq -n '{version: 1}'
  fi
}

bastion_state_write_json() {
  local json="$1"
  local f tmp

  bastion_state_init
  f="$(bastion_state_file)"
  tmp="$(mktemp "$(bastion_state_dir)/state.XXXXXX")"
  printf '%s\n' "$json" > "$tmp"
  chmod 0600 "$tmp"
  mv "$tmp" "$f"
}
