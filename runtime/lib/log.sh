#!/usr/bin/env bash

# --------------------------------------------------
# Bastion logging library
# --------------------------------------------------

: "${LOG_LEVEL:=INFO}"
: "${LOG_TS:=1}"
: "${LOG_FILE:=}"

_log_level_num() {
  case "$1" in
    DEBUG) echo 10 ;;
    INFO) echo 20 ;;
    WARN) echo 30 ;;
    ERROR) echo 40 ;;
    *) echo 20 ;;
  esac
}

_should_log() {
  [[ $(_log_level_num "$1") -ge $(_log_level_num "$LOG_LEVEL") ]]
}

_log_ts() {
  [[ "$LOG_TS" == "1" ]] && date +"%Y-%m-%dT%H:%M:%S%z"
}

_log_write() {
  local level="$1"
  shift
  local msg="$*"
  local ts=""

  ts="$(_log_ts)"
  local line=""

  if [[ -n "$ts" ]]; then
    line="${ts} [$level] [$PROGRAM_NAME] $msg"
  else
    line="[$level] [$PROGRAM_NAME] $msg"
  fi

  # stdout vs stderr split
  if [[ "$level" == "ERROR" || "$level" == "WARN" ]]; then
    echo "$line" >&2
  else
    echo "$line"
  fi

  # optional file logging
  if [[ -n "$LOG_FILE" ]]; then
    echo "$line" >> "$LOG_FILE"
  fi
}

log_debug() {
  _should_log DEBUG && _log_write DEBUG "$@"
  true
}
log_info() {
  _should_log INFO && _log_write INFO "$@"
  true
}
log_warn() {
  _should_log WARN && _log_write WARN "$@"
  true
}
log_error() { _log_write ERROR "$@"; }
