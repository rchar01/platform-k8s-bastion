#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

run_test() {
  local name="$1"
  local script="$2"

  printf '==> %s\n' "$name"
  bash "$script"
}

main() {
  run_test "Runtime install manifest" "${SCRIPT_DIR}/scenarios/test-install-manifest.sh"
}

main "$@"
