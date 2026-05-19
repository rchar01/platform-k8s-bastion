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

require_arg() {
  local opt="$1"
  local value="${2:-}"

  [[ -n "$value" && "$value" != --* ]] || die "Missing value for ${opt}"
}

dns1123_name_with_hash() {
  local raw="$1"
  local suffix="${2:-}"
  local hash prefix max_prefix

  [[ -n "$raw" ]] || die "Cannot build DNS-1123 name from empty input"

  hash="$(printf '%s' "$raw" | sha256sum | cut -c1-10)"
  prefix="$(printf '%s' "$raw" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
  [[ -n "$prefix" ]] || prefix="user"

  if [[ -n "$suffix" ]]; then
    suffix="$(printf '%s' "$suffix" \
      | tr '[:upper:]' '[:lower:]' \
      | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//')"
    suffix="${suffix:0:120}"
    suffix="$(printf '%s' "$suffix" | sed -E 's/-+$//')"
  fi

  if [[ -n "$suffix" ]]; then
    max_prefix=$((253 - ${#hash} - ${#suffix} - 2))
    prefix="${prefix:0:max_prefix}"
    prefix="$(printf '%s' "$prefix" | sed -E 's/-+$//')"
    [[ -n "$prefix" ]] || prefix="user"
    printf '%s-%s-%s\n' "$prefix" "$suffix" "$hash"
  else
    max_prefix=$((253 - ${#hash} - 1))
    prefix="${prefix:0:max_prefix}"
    prefix="$(printf '%s' "$prefix" | sed -E 's/-+$//')"
    [[ -n "$prefix" ]] || prefix="user"
    printf '%s-%s\n' "$prefix" "$hash"
  fi
}
