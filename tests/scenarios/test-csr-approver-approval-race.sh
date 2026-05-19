#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
APPROVER="${ROOT_DIR}/runtime/sbin/bastion-csr-approver"

[[ -f "$APPROVER" ]] || {
  printf 'Missing CSR approver: %s\n' "$APPROVER" >&2
  exit 1
}

if grep -q 'kubectl certificate approve' "$APPROVER"; then
  printf 'CSR approver still approves by name with kubectl certificate approve\n' >&2
  exit 1
fi

required_patterns=(
  'metadata.uid'
  'metadata.resourceVersion'
  '/apis/certificates.k8s.io/v1/certificatesigningrequests/${csr}/approval'
  'kubectl replace --raw "$approval_path" -f -'
  'lastTransitionTime: $now'
  'reason=csr_changed'
)

for pattern in "${required_patterns[@]}"; do
  if ! grep -Fq "$pattern" "$APPROVER"; then
    printf 'CSR approver missing expected race-hardening pattern: %s\n' "$pattern" >&2
    exit 1
  fi
done

printf 'CSR approver approval race hardening check passed\n'
