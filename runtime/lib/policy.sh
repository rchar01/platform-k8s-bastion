#!/usr/bin/env bash

POLICY_LINUX_NAME_PATTERN='^[a-z_][a-z0-9_-]{0,31}$'

policy_validate_linux_name() {
  local kind="$1"
  local name="$2"

  [[ -n "$name" ]] || die "${kind} is empty"
  [[ "$name" =~ $POLICY_LINUX_NAME_PATTERN ]] || die "${kind} must match ${POLICY_LINUX_NAME_PATTERN}: ${name}"
}

policy_validate_identity_names() {
  local policy="${1:-${POLICY_FILE:-/etc/bastion/access-policy.yaml}}"
  local daemon_allowed_group group_prefix group user

  [[ -f "$policy" ]] || die "Policy file not found: $policy"

  daemon_allowed_group="$(yq -r '.daemon.allowedLoginGroup // ""' "$policy")"
  group_prefix="$(yq -r '.csr.groupPrefix // ""' "$policy")"

  policy_validate_linux_name "daemon.allowedLoginGroup" "$daemon_allowed_group"
  policy_validate_linux_name "csr.groupPrefix" "$group_prefix"

  while IFS= read -r group; do
    [[ -n "$group" ]] || continue
    policy_validate_linux_name "policy group" "$group"
  done < <(yq -r '(.groups // {}) | keys[]' "$policy")

  while IFS= read -r user; do
    [[ -n "$user" ]] || continue
    policy_validate_linux_name "policy user" "$user"

    while IFS= read -r group; do
      [[ -n "$group" ]] || continue
      policy_validate_linux_name "policy ensureGroups entry for ${user}" "$group"
    done < <(USER_KEY="$user" yq -r '(.users[strenv(USER_KEY)].ensureGroups // []) | .[]' "$policy")
  done < <(yq -r '(.users // {}) | keys[]' "$policy")
}

policy_read() {
  local policy="${POLICY_FILE:-/etc/bastion/access-policy.yaml}"

  [[ -f "$policy" ]] || die "Policy file not found: $policy"

  local signer cert_ttl_default cert_ttl_min cert_ttl_max renew_threshold
  local bootstrap_ttl_default bootstrap_ttl_max group_prefix
  local cluster_name cluster_server cluster_ca_file
  local daemon_allowed_group daemon_socket_path daemon_request_max_bytes
  local daemon_request_timeout daemon_failure_backoff

  signer="$(yq -r '.csr.signerName // ""' "$policy")"
  cert_ttl_default="$(yq -r '.csr.ttl.defaultSeconds // ""' "$policy")"
  cert_ttl_min="$(yq -r '.csr.ttl.minSeconds // ""' "$policy")"
  cert_ttl_max="$(yq -r '.csr.ttl.maxSeconds // ""' "$policy")"
  renew_threshold="$(yq -r '.csr.renewal.thresholdSeconds // ""' "$policy")"
  bootstrap_ttl_default="$(yq -r '.bootstrap.ttl.defaultSeconds // ""' "$policy")"
  bootstrap_ttl_max="$(yq -r '.bootstrap.ttl.maxSeconds // ""' "$policy")"
  group_prefix="$(yq -r '.csr.groupPrefix // ""' "$policy")"
  cluster_name="$(yq -r '.cluster.name // ""' "$policy")"
  cluster_server="$(yq -r '.cluster.server // ""' "$policy")"
  cluster_ca_file="$(yq -r '.cluster.caFile // ""' "$policy")"
  daemon_allowed_group="$(yq -r '.daemon.allowedLoginGroup // ""' "$policy")"
  daemon_socket_path="$(yq -r '.daemon.socket.path // ""' "$policy")"
  daemon_request_max_bytes="$(yq -r '.daemon.request.maxBytes // ""' "$policy")"
  daemon_request_timeout="$(yq -r '.daemon.request.timeoutSeconds // ""' "$policy")"
  daemon_failure_backoff="$(yq -r '.daemon.rateLimit.failureBackoffSeconds // ""' "$policy")"

  [[ -n "$signer" ]] || die "csr.signerName missing in policy"
  [[ "$cert_ttl_default" =~ ^[0-9]+$ ]] || die "csr.ttl.defaultSeconds must be integer"
  [[ "$cert_ttl_min" =~ ^[0-9]+$ ]] || die "csr.ttl.minSeconds must be integer"
  [[ "$cert_ttl_max" =~ ^[0-9]+$ ]] || die "csr.ttl.maxSeconds must be integer"
  [[ "$renew_threshold" =~ ^[0-9]+$ ]] || die "csr.renewal.thresholdSeconds must be integer"
  [[ "$bootstrap_ttl_default" =~ ^[0-9]+$ ]] || die "bootstrap.ttl.defaultSeconds must be integer"
  [[ "$bootstrap_ttl_max" =~ ^[0-9]+$ ]] || die "bootstrap.ttl.maxSeconds must be integer"
  [[ -n "$group_prefix" ]] || die "csr.groupPrefix missing in policy"
  [[ -n "$cluster_name" ]] || die "cluster.name missing in policy"
  [[ -n "$cluster_server" ]] || die "cluster.server missing in policy"
  [[ -n "$cluster_ca_file" ]] || die "cluster.caFile missing in policy"
  [[ -n "$daemon_allowed_group" ]] || die "daemon.allowedLoginGroup missing in policy"
  [[ -n "$daemon_socket_path" ]] || die "daemon.socket.path missing in policy"
  [[ "$daemon_request_max_bytes" =~ ^[0-9]+$ ]] || die "daemon.request.maxBytes must be integer"
  [[ "$daemon_request_timeout" =~ ^[0-9]+$ ]] || die "daemon.request.timeoutSeconds must be integer"
  [[ "$daemon_failure_backoff" =~ ^[0-9]+$ ]] || die "daemon.rateLimit.failureBackoffSeconds must be integer"

  policy_validate_identity_names "$policy"

  ((cert_ttl_min <= cert_ttl_default)) || die "csr.ttl.defaultSeconds must be >= csr.ttl.minSeconds"
  ((cert_ttl_default <= cert_ttl_max)) || die "csr.ttl.defaultSeconds must be <= csr.ttl.maxSeconds"
  ((renew_threshold > 0)) || die "csr.renewal.thresholdSeconds must be > 0"
  ((bootstrap_ttl_default > 0)) || die "bootstrap.ttl.defaultSeconds must be > 0"
  ((bootstrap_ttl_default <= bootstrap_ttl_max)) || die "bootstrap.ttl.defaultSeconds must be <= bootstrap.ttl.maxSeconds"
  ((daemon_request_max_bytes > 0)) || die "daemon.request.maxBytes must be > 0"
  ((daemon_request_timeout > 0)) || die "daemon.request.timeoutSeconds must be > 0"
  ((daemon_failure_backoff > 0)) || die "daemon.rateLimit.failureBackoffSeconds must be > 0"

  export CSR_SIGNER_NAME="$signer"
  export CLIENT_CERT_TTL_DEFAULT_SECONDS="$cert_ttl_default"
  export CLIENT_CERT_TTL_MIN_SECONDS="$cert_ttl_min"
  export CLIENT_CERT_TTL_MAX_SECONDS="$cert_ttl_max"
  export CLIENT_CERT_RENEW_THRESHOLD_SECONDS="$renew_threshold"
  export BOOTSTRAP_TOKEN_TTL_DEFAULT_SECONDS="$bootstrap_ttl_default"
  export BOOTSTRAP_TOKEN_TTL_MAX_SECONDS="$bootstrap_ttl_max"
  export GROUP_PREFIX="$group_prefix"
  export BASTION_CLUSTER_NAME="$cluster_name"
  export BASTION_CLUSTER_SERVER="$cluster_server"
  export BASTION_CLUSTER_CA_FILE="$cluster_ca_file"
  export DAEMON_ALLOWED_LOGIN_GROUP="$daemon_allowed_group"
  export DAEMON_SOCKET_PATH="$daemon_socket_path"
  export DAEMON_REQUEST_MAX_BYTES="$daemon_request_max_bytes"
  export DAEMON_REQUEST_TIMEOUT_SECONDS="$daemon_request_timeout"
  export DAEMON_FAILURE_BACKOFF_SECONDS="$daemon_failure_backoff"
}
