#!/usr/bin/env bash

log() { echo "[$PROGRAM_NAME] $*"; }

# Normalize PATH so bastion-installed commands in /usr/local are resolvable
# under sudo/root environments that omit sbin or /usr/local entries.
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:${PATH:-}"

die() {
  local msg="$*"
  if declare -F log_error > /dev/null 2>&1; then
    log_error "$msg"
  else
    echo "ERROR: $msg" >&2
  fi
  exit 1
}

require_root() {
  [[ $EUID -eq 0 ]] || {
    echo "Run as root"
    exit 1
  }
}

need_cmd() {
  command -v "$1" > /dev/null 2>&1 || {
    echo "Missing command: $1"
    exit 1
  }
}
