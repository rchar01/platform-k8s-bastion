SHELL := /bin/bash

SHFMT_TARGETS := runtime/bin runtime/internal-bin runtime/sbin runtime/lib tests/scenarios tests/run-all.sh

.PHONY: help fmt-shell fmt-shell-check lint-shell check-shell test

help:
	@printf '%s\n' \
	  'Available targets:' \
	  '  fmt-shell              Format shell files with shfmt' \
	  '  fmt-shell-check        Check shell formatting (fails on diffs)' \
	  '  lint-shell             Run shellcheck on shell scripts' \
	  '  check-shell            Run shell format + lint checks' \
	  '  test                   Run runtime metadata checks'

fmt-shell:
	shfmt -i 2 -ci -sr -bn -w $(SHFMT_TARGETS)

fmt-shell-check:
	shfmt -i 2 -ci -sr -bn -d $(SHFMT_TARGETS)

lint-shell:
	bash -O globstar -O nullglob -c 'shellcheck -x -S warning -e SC1090,SC2034 ./runtime/bin/* ./runtime/internal-bin/* ./runtime/sbin/* ./runtime/lib/*.sh ./tests/**/*.sh'

check-shell: fmt-shell-check lint-shell

test:
	./tests/run-all.sh
