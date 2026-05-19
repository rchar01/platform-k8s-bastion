#!/usr/bin/env python3
"""Unit tests for bastion_bootstrapd concurrency helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import threading
import types
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "runtime/lib/python/bastion_bootstrapd.py"

spec = importlib.util.spec_from_file_location("bastion_bootstrapd", MODULE_PATH)
assert spec is not None and spec.loader is not None
bastion_bootstrapd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bastion_bootstrapd)


class BootstrapDaemonConcurrencyTests(unittest.TestCase):
    def daemon(self):
        daemon = bastion_bootstrapd.BootstrapDaemon.__new__(bastion_bootstrapd.BootstrapDaemon)
        daemon.inflight_locks = {}
        daemon.inflight_global_lock = threading.Lock()
        daemon.connection_semaphore = threading.BoundedSemaphore(1)
        daemon.request_timeout = 1
        return daemon

    def test_limited_connection_releases_semaphore_on_handler_error(self) -> None:
        daemon = self.daemon()
        daemon.connection_semaphore.acquire(blocking=False)

        def fail_handler(_conn):
            raise RuntimeError("handler failed")

        daemon.handle_connection = fail_handler

        with self.assertRaises(RuntimeError):
            daemon.handle_connection_limited(object())

        self.assertTrue(daemon.connection_semaphore.acquire(blocking=False))

    def test_revoke_uses_existing_uid_lock(self) -> None:
        daemon = self.daemon()
        user = types.SimpleNamespace(pw_name="alice")
        lock = daemon.inflight_lock_for_uid(1000)
        self.assertTrue(lock.acquire(blocking=False))
        self.addCleanup(lock.release)

        with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "busy"):
            daemon.dispatch("revoke-bootstrap", 1000, user, {"tokenId": "abc123"})

    def test_issue_and_revoke_share_uid_lock(self) -> None:
        daemon = self.daemon()
        self.assertIs(daemon.inflight_lock_for_uid(1000), daemon.inflight_lock_for_uid(1000))

    def test_socket_path_must_be_under_runtime_dir(self) -> None:
        with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "under /run/bastion-bootstrapd"):
            bastion_bootstrapd.normalize_socket_path("/tmp/bootstrapd.sock")

    def test_socket_path_must_be_direct_child(self) -> None:
        with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "direct child"):
            bastion_bootstrapd.normalize_socket_path("/run/bastion-bootstrapd/nested/bootstrapd.sock")

    def test_socket_path_normalizes_allowed_direct_child(self) -> None:
        self.assertEqual(
            bastion_bootstrapd.normalize_socket_path("/run/bastion-bootstrapd/./bootstrapd.sock"),
            "/run/bastion-bootstrapd/bootstrapd.sock",
        )

    def test_stale_socket_removal_rejects_non_socket(self) -> None:
        daemon = self.daemon()
        daemon.socket_path = __file__

        with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "non-socket"):
            daemon.remove_stale_socket()


if __name__ == "__main__":
    unittest.main()
