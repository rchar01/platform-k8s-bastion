# Kubernetes App Requirements

This document defines the Kubernetes-side app contract required by the
`platform-k8s-bastion` runtime.

`platform-k8s-bastion` does not deploy these apps. `platform-config` owns the
manifests, RBAC, Service objects, systemd wiring, and cluster configuration that
make this contract available to bastion hosts. Current host-side runtime commands
such as `bastion-csr-approver` and `bastion-csr-cleanup` remain in this runtime
until an external controller replacement is explicitly adopted.

## Ownership Boundary

`platform-k8s-bastion` owns:

- runtime commands installed on bastion hosts
- shell and Python libraries used by those commands
- the integration contract in this document
- current host-side CSR approval and cleanup commands
- runtime version and install metadata

`platform-config` owns:

- deployment of Kubernetes-side apps and manifests
- namespace, ServiceAccount, Service, RBAC, and workload resources
- host installation and `/etc/bastion` configuration
- systemd services and timers that run host-side runtime commands
- smoke tests that exercise a real cluster

`platform-private` owns:

- real inventories
- non-secret cluster-specific configuration
- access-policy inputs

Secrets such as admin kubeconfigs, bootstrap tokens, private keys, and signing
keys must remain outside Git.

## Required Kubernetes Apps

The full per-user bootstrap flow expects these Kubernetes-side capabilities:

- `bootstrap-token-issuer`
- `bootstrap-cert-controller`

`bootstrap-cert-controller` may replace the current host-side CSR approval and
cleanup commands after its signer and trust model are explicitly adopted. It may
be implemented as one controller app or split into separate approver, signer, and
cleanup controllers. The external shape is less important than preserving the
contracts below.

## Fixed Integration Constants

The runtime currently uses fixed integration values from two places. Most are
defined in `runtime/lib/contract.sh`; the token issuer Service name and Service
port name are currently hardcoded in
`runtime/sbin/bastion-bootstrap-token-issue` and
`runtime/sbin/bastion-bootstrap-token-revoke`:

```text
controller namespace: bastion-system
token issuer service: bastion-token-issuer
token issuer service port name: http
bootstrap auth group: system:bootstrappers:platform-users
bootstrap token namespace: kube-system
token issuer service account: bastion-token-issuer
CSR approver service account: bastion-csr-approver
CSR signer service account: bastion-csr-signer
CSR cleanup service account: bastion-csr-cleanup
```

If `platform-config` needs to make these configurable, update this runtime
contract and all dependent runtime commands in the same release.

## Bootstrap Token Issuer

The runtime calls the token issuer through the Kubernetes API server service
proxy with the admin kubeconfig:

```text
/api/v1/namespaces/bastion-system/services/bastion-token-issuer:http/proxy
```

The Service must be reachable with `kubectl create --raw` from the bastion
admin kubeconfig.

### Issue Endpoint

Endpoint:

```text
POST /v1/bootstrap-token/issue
```

Request body:

```json
{
  "user": "alice",
  "reason": "login-recovery",
  "ttlSeconds": 600
}
```

`reason` must support these values:

- `initial-enrollment`
- `login-recovery`
- `manual-recovery`

`ttlSeconds` must be honored within the policy-defined bootstrap token TTL
limits. The runtime validates these values before calling the issuer, and the
issuer should validate them again as a trust boundary.

Successful response body:

```json
{
  "tokenId": "example-token-id",
  "expiresAt": "2026-05-20T12:34:56Z",
  "bootstrapKubeconfig": "apiVersion: v1\nkind: Config\n..."
}
```

Response requirements:

- `tokenId` must be non-empty and must identify the bootstrap credential.
- `expiresAt` must be an RFC3339 UTC timestamp parseable by the runtime.
- `bootstrapKubeconfig` must be a complete kubeconfig that can submit CSRs.
- The bootstrap kubeconfig must authenticate as `system:bootstrap:<token-id>`.
- The authenticated identity must include
  `system:bootstrappers:platform-users`.

Security requirements:

- Token TTL must be short-lived and bounded by policy.
- Token issue must be auditable without logging raw bearer token material.
- Token IDs should be treated as sensitive in logs outside root-only caches.
- The token must only grant permissions needed for bastion certificate
  bootstrap.
- If the runtime cannot record local token ownership state after issue, best
  effort revoke must invalidate the token.

### Revoke Endpoint

Endpoint:

```text
POST /v1/bootstrap-token/revoke
```

Request body:

```json
{
  "tokenId": "example-token-id"
}
```

Response requirements:

- A successful response may be an empty body or JSON status body.
- Revoke should be idempotent.
- Revoking an already expired or already revoked token should not resurrect it.
- After revoke succeeds, the token must no longer authenticate to submit CSRs.

Security requirements:

- Revoke errors must not require logging raw token IDs.
- Revoke must remove or invalidate the Kubernetes-side token backing object.
- Revoke should complete quickly enough for login recovery cleanup paths.

## Bootstrap Cert Controller

The certificate controller capability handles bastion client certificate CSRs.
It may be implemented as one controller or split into approver, signer, and
cleanup controllers.

### CSR Selection

The controller must only process CSRs that match the bastion contract:

- object kind: `certificates.k8s.io/v1 CertificateSigningRequest`
- label: `bastion-access=true`
- signer name: policy `.csr.signerName`
- usage exactly compatible with `client auth`
- `expirationSeconds` within policy `.csr.ttl.minSeconds` and
  `.csr.ttl.maxSeconds`

The runtime creates CSRs with DNS-1123-compatible names and a hash suffix for
uniqueness. Controller logic must not rely on CSR names for authorization.

### Subject Validation

The controller must decode the CSR request and validate the subject:

- `CN` is the target Linux username.
- `CN` must not start with `system:`.
- `O` values are requested Kubernetes groups.
- OpenSSL subject output with either `CN=alice` or `CN = alice` formatting must
  be accepted.

The controller must validate that requested groups are allowed for the target
user according to the same policy and host-group model used by the runtime.

### Requester Validation

For normal renewal CSRs:

- `.spec.username` must equal the subject `CN`.

For bootstrap CSRs:

- `.spec.username` must be `system:bootstrap:<token-id>`.
- `.spec.groups` must include `system:bootstrappers:platform-users`.
- The token ID must map to the same subject `CN` in the bastion token ownership
  cache or an equivalent authoritative token ownership source.
- The ownership entry must be unexpired.

Expired ownership entries must not authorize CSR approval.

### Duplicate Pending Protection

The controller must avoid approving duplicate pending CSRs for the same
requester. A safe implementation should deny or skip a CSR if another pending
bastion CSR exists with the same `.spec.username` and no terminal condition.

### Approval Update Safety

Before approving a CSR, the controller must re-read the current object and bind
approval to the validated object identity:

- `metadata.uid`
- `metadata.resourceVersion`

If either value changed after validation, the controller must not approve that
CSR. Approval should be written through the CSR approval subresource.

### Signing Options

The platform can choose either model:

- Use a Kubernetes signer that watches approved CSRs for the configured signer
  name and writes `.status.certificate`.
- Implement a dedicated signer controller that signs approved bastion CSRs and
  writes `.status.certificate`.

In either model, the signed certificate must be valid for Kubernetes client auth
and must respect the requested and policy-bounded expiration.

### Cleanup

Cleanup must delete only old approved bastion CSRs:

- label `bastion-access=true`
- matching signer name
- status condition includes `Approved`
- older than the configured retention window

Cleanup must not delete pending, denied, wrong-signer, or unlabeled CSRs.

## RBAC Requirements

The admin kubeconfig used by the bastion host must be able to reach the token
issuer Service through the API server proxy.

The token issuer needs permissions appropriate to its token backend. If it uses
Kubernetes bootstrap token Secrets, it needs tightly scoped permissions to
create, read, update, and delete only the required token Secret objects in the
configured namespace.

The cert controller needs permissions to:

- get, list, and watch `certificatesigningrequests`
- update the CSR approval subresource
- update CSR status if it signs certificates itself
- delete old approved bastion CSRs if it owns cleanup
- read any ConfigMaps or Secrets that contain non-runtime controller config

RBAC should be least privilege and split by ServiceAccount when the app is split
into issuer, approver, signer, and cleanup components.

## Runtime Failure Expectations

The Kubernetes apps must support these runtime failure behaviors:

- issue failure returns a non-success response and does not create a usable token
- revoke failure leaves host-side token ownership cache intact unless the
  command is explicitly best-effort
- expired tokens cannot authorize later CSR approval
- controller restarts are safe and reconcile pending work without duplicate
  approval
- audit logs redact bootstrap token IDs and bearer tokens
- invalid TTL, invalid reason, bad signer, bad usage, unknown user, group
  mismatch, duplicate pending CSR, and changed CSR identity all result in deny or
  explicit error behavior

## Test Expectations for platform-config

`platform-config` should own live-cluster tests that prove this contract works
against a real Kubernetes API.

Minimum smoke coverage:

- token issue returns `tokenId`, `expiresAt`, and usable bootstrap kubeconfig
- token revoke invalidates the token
- bootstrap kubeconfig can submit a bastion-labeled CSR
- valid bootstrap CSR is approved and signed
- expired or mismatched token ownership does not approve a CSR
- renewal CSR for an existing user is approved and signed
- duplicate pending CSRs are not both approved
- cleanup deletes only old approved bastion CSRs
- audit output does not expose raw bootstrap token IDs or bearer tokens
