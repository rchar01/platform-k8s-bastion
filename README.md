<div align="center">
  <img src="assets/brand/platform-k8s-bastion-forge-avatar-transparent-512.png" width="256" alt="Kubernetes Bastion Runtime logo">

  <h1>Kubernetes Bastion Runtime</h1>

  <p>Runtime commands and libraries for Kubernetes bastion hosts.</p>
</div>

---

`platform-k8s-bastion` is the runtime artifact source for Kubernetes bastion hosts.

Host installation, OS packages, external CLI downloads, `/etc/bastion` files, login profile, and systemd units are owned by `platform-config` Ansible. This repository intentionally does not install or configure hosts directly.

## Platform Repository Roles

The platform repositories are split by responsibility:

| Repository | Purpose |
| --- | --- |
| [`platform-k8s-bastion`](https://codeberg.org/rch/platform-k8s-bastion) | Provides the runtime commands, libraries, and install manifest consumed by bastion hosts. |
| [`platform-config`](https://codeberg.org/rch/platform-config) | Installs this runtime, writes host configuration, deploys Kubernetes-side apps, manages systemd/login integration, and runs live smoke tests. |
| `platform-private` | Stores real inventories, access policies, and non-secret cluster-specific config. |
| [`platform-tools`](https://codeberg.org/rch/platform-tools) | Provides optional public helper commands, including `platform-bastion-policy` for validating and rendering bastion access-policy inputs. |

Secret material such as admin kubeconfigs, tokens, private keys, and signing keys
belongs outside Git.

## Layout

Installable runtime files live under `runtime/`:

```text
runtime/
  VERSION
  install-manifest.yml
  bin/
  internal-bin/
  sbin/
  lib/
  lib/python/
```

`platform-config` vendors this repository and installs from:

```text
vendor/platform-k8s-bastion/runtime
```

## Boundary

This repository owns:

- public user commands in `runtime/bin/`
- internal helpers in `runtime/internal-bin/`
- admin/operator commands in `runtime/sbin/`
- shared shell libraries in `runtime/lib/`
- Python daemon modules in `runtime/lib/python/`
- runtime install metadata in `runtime/install-manifest.yml`

`platform-config` owns:

- installing OS packages
- downloading external tools such as `kubectl`, `helm`, `jq`, `yq`, and registry tools
- copying this runtime into `/usr/local`
- writing `/etc/bastion/access-policy.yaml`, `/etc/bastion/admin.kubeconfig`, and `/etc/bastion/ca.crt`
- deploying Kubernetes-side apps required by `docs/kubernetes-app-requirements.md`
- writing `/etc/profile.d/bastion-login.sh`
- managing systemd services and timers
- running Ansible smoke tests
- rendering runtime and external tool visibility in the login profile

`platform-private` owns real inventories, access policies, and non-secret cluster-specific config. Secret material such as admin kubeconfigs, tokens, private keys, and signing keys belongs outside Git.

`platform-tools` provides optional public tooling such as `platform-bastion-policy` for validating and rendering bastion access-policy inputs before `platform-config` applies them.

## Policy Flow

Access-policy authoring and rendering happen before this runtime consumes the
host file:

```text
platform-private access-policy input
  -> platform-tools platform-bastion-policy validation and rendering
  -> platform-config installs /etc/bastion/access-policy.yaml
  -> platform-k8s-bastion runtime consumes the installed policy
```

The runtime reads the installed host policy from `/etc/bastion/access-policy.yaml`.
It does not merge policy overlays or apply Kubernetes resources directly.

## Installed Commands

Public commands:

- `bastion-renew-cert`
- `bastion-kubeconfig-expiry`
- `bastion-version`

Admin/operator commands:

- `bastion-audit-kube-dirs`
- `bastion-bootstrap-admin-kubeconfig`
- `bastion-bootstrap-kubeconfig`
- `bastion-bootstrap-token-issue`
- `bastion-bootstrap-token-revoke`
- `bastion-bootstrap-user-groups`
- `bastion-bootstrapd`
- `bastion-cert-renew-all`
- `bastion-cluster-probe`
- `bastion-csr-approver`
- `bastion-csr-cleanup`
- `bastion-disable-user`

## Development

Shell quality checks:

```bash
make check-shell
```

Runtime metadata checks:

```bash
make test
```

End-to-end host installation tests belong in `platform-config`, not here.

Bastion access-policy validation and rendering helpers live in `platform-tools`,
not in this runtime repository.

Kubernetes-side app requirements for the bootstrap token issuer and certificate
controller are documented in `docs/kubernetes-app-requirements.md`.

## Release

The installed runtime version is stored in `runtime/VERSION`. Runtime releases
are intended to be pinned by `platform-config` as a git submodule tag, for
example:

```bash
git -C vendor/platform-k8s-bastion checkout v1.1.3
```

When a tag changes installed runtime behavior, `runtime/VERSION` should match
that tag. Documentation-only tags may leave `runtime/VERSION` unchanged because
the installed runtime has not changed.

`runtime/install-manifest.yml` is the install contract consumed by
`platform-config`. Changes that add, remove, or move runtime commands should
update the manifest, tests, `CHANGELOG.md`, and `NEWS.md` in the same release.

Release notes:

- `NEWS.md` provides a short operator-facing upgrade summary.
- `CHANGELOG.md` provides the detailed release record.

## Security

- Real kubeconfigs, tokens, private keys, and certificates must not be committed here.
- Users can request certificates but cannot approve them or request arbitrary groups.
- Admins enforce access through host group membership, policy-driven bootstrap, and CSR approval.
- Certificates are short-lived and renewed through the installed runtime commands.
- Root-run runtime commands use fixed audit/log destinations and do not honor
  environment-provided log file paths.
- `bastion-disable-user` removes bastion-managed kubeconfig files instead of
  preserving disabled backup copies.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
