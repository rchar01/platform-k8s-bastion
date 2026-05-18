#!/usr/bin/env bash

: "${BASTION_AUDIT_LOG:=/var/log/bastion-audit.log}"

audit_event() {
  local action="$1"
  local outcome="$2"
  local details="${3:-}"

  local ts actor line
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  actor="${SUDO_USER:-${USER:-unknown}}"

  line="{\"ts\":\"${ts}\",\"program\":\"${PROGRAM_NAME:-unknown}\",\"action\":\"${action}\",\"outcome\":\"${outcome}\",\"actor\":\"${actor}\",\"details\":\"${details}\"}"

  logger -t "${PROGRAM_NAME:-bastion}" -- "$line" || true

  if [[ -n "${BASTION_AUDIT_LOG:-}" ]]; then
    if [[ -w "$BASTION_AUDIT_LOG" || ! -e "$BASTION_AUDIT_LOG" ]]; then
      printf '%s\n' "$line" >> "$BASTION_AUDIT_LOG" 2> /dev/null || true
    fi
  fi
}
