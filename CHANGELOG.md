# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
and adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Document Kubernetes-side app requirements for the bootstrap token issuer and
  certificate controller deployment boundary with `platform-config`.

### Changed

- Clarify README repository boundaries, policy flow, and optional
  `platform-tools` access-policy helper usage.

## [1.1.3] - 2026-05-20

### Fixed

- Decode bootstrap daemon Unix peer credentials in Linux `pid, uid, gid` order.
- Parse OpenSSL CSR subjects with spaced `CN =` and `O =` fields.
- Redact daemon command failure details that may contain bootstrap token IDs.
- Require unexpired bootstrap token ownership cache entries during CSR approval.
- Remove disabled user kubeconfig files through the safe FD-based writer instead
  of root-renaming user-controlled paths.
- Remove stale bootstrap kubeconfigs after daemon token revoke using FD-based
  cleanup.
- Ignore environment-controlled audit and log file path overrides for root
  commands.
- Validate daemon bootstrap request TTL and reason before invoking token issuer.

## [1.1.2] - 2026-05-19

### Fixed

- Redact bootstrap token IDs from runtime audit and login state files while
  retaining root-only ownership caches for CSR owner validation.

## [1.1.1] - 2026-05-19

### Fixed

- Install user and admin kubeconfigs through a shared FD-based writer that opens
  home and `.kube` directories with `O_NOFOLLOW` and rejects symlinked targets.
- Bind CSR approval to the validated CSR `uid` and `resourceVersion` before
  writing the approval subresource.
- Restrict the bootstrap daemon socket path to `/run/bastion-bootstrapd` and
  refuse to unlink non-socket or non-root-owned stale paths.
- Generate DNS-1123-compatible CSR object names with a hash suffix for enrollment
  and renewal.

## [1.1.0] - 2026-05-19

### Fixed

- Record bootstrap token ownership in the token issue/revoke commands so direct
  token issuance can be matched by the CSR approver.
- Include `runtime/VERSION` in the install manifest contract used by
  `bastion-version`.
- Use indexed policy lookups for usernames and emit audit events as escaped JSON.
- Bound bootstrap daemon connection handling and avoid fixed `/tmp` login
  bootstrap diagnostic paths.
- Return controlled errors for runtime options that are missing required values.
- Restrict CSR cleanup to approved CSRs and improve `bastion-kubeconfig-expiry`
  help and `WARN_DAYS` validation.

## [1.0.1] - 2026-05-18

### Added

- Add project brand assets and display the transparent logo in the README.

## [1.0.0] - 2026-05-18

### Added

- Add runtime-only repository layout under `runtime/`.
- Add `runtime/VERSION` with initial runtime version `1.0.0`.
- Add `runtime/install-manifest.yml` as the install contract consumed by
  `platform-config` Ansible.
- Add public user commands under `runtime/bin/`:
  `bastion-renew-cert`, `bastion-kubeconfig-expiry`, and `bastion-version`.
- Add internal helper commands under `runtime/internal-bin/` for login bootstrap,
  daemon client access, kube state inspection, and certificate enrollment.
- Add admin/operator commands under `runtime/sbin/` for user bootstrap, admin
  kubeconfig bootstrap, token issue/revoke, CSR approval/cleanup, cluster status,
  certificate renewal, auditing, and user disablement.
- Add shared shell libraries under `runtime/lib/` and Python daemon modules under
  `runtime/lib/python/`.
- Add lightweight runtime metadata checks with `make test`.
- Add shell formatting and lint targets with `make check-shell`,
  `make fmt-shell-check`, and `make lint-shell`.

### Changed

- Define `platform-k8s-bastion` as a runtime artifact source, not a host
  installer.
- Move host installation responsibility to `platform-config`, including OS
  packages, external CLI downloads, `/etc/bastion` inputs, login profile
  rendering, systemd unit management, and Ansible smoke tests.
- Treat `runtime/install-manifest.yml` as the source of truth for runtime command
  installation and command visibility in `platform-config`.
- Keep runtime command visibility lists in Ansible-generated profile data instead
  of separate runtime text files.
- Document that private non-secret configuration belongs in `platform-private`
  and secret material belongs outside Git.

### Removed

- Remove direct host install, download, Podman fixture, and live-cluster workflow
  ownership from this repository.
- Remove legacy direct installer assets such as `download.sh`, `download.conf`,
  public `access-policy.yaml`, `justfile`, and obsolete direct test lanes.
- Remove runtime-owned `user-tools.txt` and `admin-tools.txt`; `platform-config`
  now renders profile tool visibility from Ansible variables and the manifest.
- Remove obsolete documentation that described host installation workflows now
  owned by `platform-config`.
