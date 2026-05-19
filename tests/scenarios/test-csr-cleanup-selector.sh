#!/usr/bin/env bash
set -euo pipefail

need_cmd() {
  command -v "$1" > /dev/null 2>&1 || {
    printf 'Missing command: %s\n' "$1" >&2
    exit 1
  }
}

need_cmd jq

selector="$(
  cat << 'JQ'
  .items[]
  | select(.metadata.labels["bastion-access"] == "true")
  | select(.spec.signerName == $signer)
  | select(any(.status.conditions[]?; .type == "Approved"))
  | . as $csr
  | select((.metadata.creationTimestamp | fromdateiso8601) < ($now - $retention))
  | $csr.metadata.name
JQ
)"

fixture='{
  "items": [
    {
      "metadata": {
        "name": "old-approved",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "labels": {"bastion-access": "true"}
      },
      "spec": {"signerName": "example.com/bastion"},
      "status": {"conditions": [{"type": "Approved"}]}
    },
    {
      "metadata": {
        "name": "old-pending",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "labels": {"bastion-access": "true"}
      },
      "spec": {"signerName": "example.com/bastion"},
      "status": {}
    },
    {
      "metadata": {
        "name": "old-denied",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "labels": {"bastion-access": "true"}
      },
      "spec": {"signerName": "example.com/bastion"},
      "status": {"conditions": [{"type": "Denied"}]}
    },
    {
      "metadata": {
        "name": "new-approved",
        "creationTimestamp": "2026-05-18T12:00:00Z",
        "labels": {"bastion-access": "true"}
      },
      "spec": {"signerName": "example.com/bastion"},
      "status": {"conditions": [{"type": "Approved"}]}
    },
    {
      "metadata": {
        "name": "wrong-label",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "labels": {"bastion-access": "false"}
      },
      "spec": {"signerName": "example.com/bastion"},
      "status": {"conditions": [{"type": "Approved"}]}
    },
    {
      "metadata": {
        "name": "wrong-signer",
        "creationTimestamp": "2026-01-01T00:00:00Z",
        "labels": {"bastion-access": "true"}
      },
      "spec": {"signerName": "example.com/other"},
      "status": {"conditions": [{"type": "Approved"}]}
    }
  ]
}'

actual="$(jq -r \
  --arg signer "example.com/bastion" \
  --argjson now 1770000000 \
  --argjson retention 1209600 \
  "$selector" <<< "$fixture")"

if [[ "$actual" != "old-approved" ]]; then
  printf 'Unexpected CSR cleanup selector result: %s\n' "$actual" >&2
  exit 1
fi

printf 'CSR cleanup selector fixture check passed\n'
