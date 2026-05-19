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
  run_test "Policy lookup and audit JSON safety" "${SCRIPT_DIR}/scenarios/test-policy-audit-safety.sh"
  run_test "CSR cleanup selector" "${SCRIPT_DIR}/scenarios/test-csr-cleanup-selector.sh"
  printf '==> Bootstrap daemon unit tests\n'
  python3 "${SCRIPT_DIR}/scenarios/test-bootstrap-daemon.py"
}

main "$@"
