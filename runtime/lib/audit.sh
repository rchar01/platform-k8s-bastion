#!/usr/bin/env bash

DEFAULT_BASTION_AUDIT_LOG="/var/log/bastion-audit.log"

audit_log_path() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    printf '%s\n' "$DEFAULT_BASTION_AUDIT_LOG"
  else
    printf '%s\n' "${BASTION_AUDIT_LOG:-$DEFAULT_BASTION_AUDIT_LOG}"
  fi
}

audit_event() {
  local action="$1"
  local outcome="$2"
  local details="${3:-}"

  local ts actor line audit_log
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  actor="${SUDO_USER:-${USER:-unknown}}"
  audit_log="$(audit_log_path)"

  line="$(jq -nc \
    --arg ts "$ts" \
    --arg program "${PROGRAM_NAME:-unknown}" \
    --arg action "$action" \
    --arg outcome "$outcome" \
    --arg actor "$actor" \
    --arg details "$details" \
    '{ts: $ts, program: $program, action: $action, outcome: $outcome, actor: $actor, details: $details}')"

  logger -t "${PROGRAM_NAME:-bastion}" -- "$line" || true

  if [[ -n "$audit_log" ]]; then
    if [[ -w "$audit_log" || ! -e "$audit_log" ]]; then
      printf '%s\n' "$line" >> "$audit_log" 2> /dev/null || true
    fi
  fi
}
