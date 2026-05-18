# AGENTS.md

Guidance for coding agents working in `platform-k8s-bastion`.

## Scope

- This repository is a runtime artifact source for `platform-config` Ansible.
- Installable files live under `runtime/`.
- Host installation and configuration belong in `platform-config`, not here.
- Real inventories, access policies, and non-secret cluster-specific config belong in `platform-private`; admin kubeconfigs, tokens, private keys, and other secrets belong outside Git.

## Layout

- `runtime/bin/`: public user commands.
- `runtime/internal-bin/`: internal helper commands.
- `runtime/sbin/`: admin/root-facing commands.
- `runtime/lib/`: shared shell libraries.
- `runtime/lib/python/`: Python daemon modules.
- `runtime/install-manifest.yml`: runtime install contract.
- `tests/`: lightweight runtime metadata checks only.

## Commands

- `make help` - show available targets.
- `make check-shell` - run shell formatting check and shellcheck.
- `make test` - run runtime metadata checks.
- `make fmt-shell` - format runtime and test shell files.
- `make fmt-shell-check` - check shell formatting.
- `make lint-shell` - run shellcheck.

Do not add direct install, download, Podman fixture, or live-cluster workflows back to this repository. Add host install tests to `platform-config` instead.

## Rules

- Keep changes focused and minimal.
- Never add secrets, kubeconfigs, tokens, or private keys.
- If command behavior changes, update `runtime/install-manifest.yml`, tests, and docs as needed.
- Preserve least-privilege boundaries between public commands, internal helpers, and admin commands.
- Use `#!/usr/bin/env bash` and `set -euo pipefail` for executable shell scripts unless there is a concrete reason not to.
- Run `make check-shell` and `make test` after runtime changes.

## Agent Workflow Expectations

- Read relevant code before editing.
- Prefer minimal changes that match existing patterns.
- Keep `README.md`, `AGENTS.md`, and skill docs current when repository behavior changes.
- If your runtime provides specialized tools or subagents for codebase exploration, use them when repository structure, ownership boundaries, or relevant files are unclear.
- If your runtime provides specialized tools or subagents for verification, use them for non-trivial test runs, runtime-backed checks, or command-heavy validation.
- If your runtime provides specialized tools or subagents for review, use them after substantial edits to catch regressions, missing updates, or doc/code drift.
- If your runtime provides specialized tools or subagents for research, use them when behavior depends on external tooling or upstream docs.
- Prefer local repository docs, scripts, and configuration first; use web research when local sources are insufficient or freshness matters.
- Summarize any specialist-tool or subagent findings you rely on.
- Do not revert unrelated worktree changes.
