# Runtime Tests

This directory contains lightweight runtime metadata checks only.

Host installation, live cluster tests, Podman fixtures, and smoke tests belong in `platform-config`, because Ansible owns the bastion host workflow.

## Run

```bash
make test
```

Current checks verify that `runtime/install-manifest.yml` and the installable runtime layout stay in sync.
