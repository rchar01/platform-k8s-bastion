# News

This file gives a short, release-oriented view of what changed between versions.

## Unreleased

Runtime correctness and bootstrap hardening updates.

Highlights:

- Bootstrap token ownership is now recorded by token issue/revoke commands.
- The install manifest now includes `runtime/VERSION` for `bastion-version`.
- Policy username lookups and audit event JSON handling are now safer.
- Bootstrap daemon concurrency is bounded and login bootstrap diagnostics no
  longer use fixed `/tmp` paths.
- Runtime commands now report missing option values consistently.

## v1.0.1 - 2026-05-18

Documentation and branding update.

Highlights:

- Added project brand assets.
- Displayed the transparent project logo in the README.

## v1.0.0 - 2026-05-18

Initial runtime-only release of `platform-k8s-bastion`.

This release makes the repository an installable runtime artifact source for
`platform-config` Ansible instead of a host installer. Runtime commands,
libraries, Python daemon modules, version metadata, and the install manifest now
live under `runtime/`.

Highlights:

- `platform-config` owns host installation, OS packages, external tool downloads,
  `/etc/bastion` files, login profile rendering, and systemd units.
- `platform-k8s-bastion` owns only runtime commands, libraries, daemon modules,
  and `runtime/install-manifest.yml`.
- `runtime/install-manifest.yml` is the contract used by Ansible to install
  public, internal, and admin commands.
- Direct install/download workflows, public access policy examples, live-cluster
  test lanes, and container fixture workflows were removed from this repository.
- Real inventories and non-secret cluster config stay in `platform-private`;
  admin kubeconfigs, tokens, private keys, and other secrets stay outside Git.
