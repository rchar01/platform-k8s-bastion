#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/runtime"
MANIFEST="${RUNTIME_DIR}/install-manifest.yml"

[[ -f "$MANIFEST" ]] || {
  printf 'Missing install manifest: %s\n' "$MANIFEST" >&2
  exit 1
}

required_files=(
  VERSION
  lib/common.sh
  lib/log.sh
  lib/contract.sh
  lib/policy.sh
  lib/audit.sh
  lib/state.sh
  lib/python/bastion_bootstrapd.py
  lib/python/bastion_bootstrapd_client.py
)

manifest_section_value() {
  local section="$1"
  local key="$2"

  awk -v section="${section}:" -v key="${key}:" '
    $0 == section { in_section = 1; next }
    in_section && /^[^[:space:]]/ { exit }
    in_section && $1 == key { print $2; exit }
  ' "$MANIFEST"
}

manifest_section_files() {
  local section="$1"

  awk -v section="${section}:" '
    $0 == section { in_section = 1; next }
    in_section && /^[^[:space:]]/ { exit }
    in_section && $1 == "-" { print $2 }
  ' "$MANIFEST"
}

for section in publicCommands internalCommands adminCommands; do
  source_dir="$(manifest_section_value "$section" sourceDir)"
  [[ -n "$source_dir" ]] || {
    printf 'Missing sourceDir for manifest section: %s\n' "$section" >&2
    exit 1
  }

  while IFS= read -r file; do
    [[ -n "$file" ]] || continue
    required_files+=("${source_dir}/${file}")
  done < <(manifest_section_files "$section")
done

for path in "${required_files[@]}"; do
  [[ -f "${RUNTIME_DIR}/${path}" ]] || {
    printf 'Runtime-required file is missing: %s\n' "$path" >&2
    exit 1
  }
done

removed_files=(
  download.sh
  download.conf
  access-policy.yaml
  admin-tools.txt
  justfile
  tools/.gitkeep
  lib/args.sh
  lib/system.sh
  tests/run-kind.sh
  user-tools.txt
)

for path in "${removed_files[@]}"; do
  [[ ! -e "${ROOT_DIR}/${path}" ]] || {
    printf 'Old workflow file still exists: %s\n' "$path" >&2
    exit 1
  }
done

printf 'Runtime install manifest check passed\n'
