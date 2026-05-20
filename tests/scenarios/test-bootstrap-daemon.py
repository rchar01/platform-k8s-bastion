#!/usr/bin/env python3
"""Unit tests for bastion_bootstrapd concurrency helpers."""

from __future__ import annotations

import importlib.util
import pathlib
import struct
import sys
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

    def test_peer_identity_uses_linux_ucred_order(self) -> None:
        daemon = self.daemon()

        class FakeConn:
            def getsockopt(self, _level, _option, _size):
                return struct.pack("3i", 4321, 1000, 1001)

        self.assertEqual(daemon.peer_identity(FakeConn()), (1000, 1001, 4321))

    def test_run_cmd_redacts_failed_command_details(self) -> None:
        secret = "secret-token-id"
        with self.assertRaises(bastion_bootstrapd.DaemonError) as ctx:
            bastion_bootstrapd.run_cmd(
                [
                    sys.executable,
                    "-c",
                    "import sys; print('secret-token-id', file=sys.stderr); sys.exit(9)",
                    "--token-id",
                    secret,
                ],
                timeout_seconds=1,
            )

        error = str(ctx.exception)
        self.assertEqual(error, "command_failed rc=9")
        self.assertNotIn(secret, error)

    def test_issue_rejects_bool_ttl(self) -> None:
        daemon = self.daemon()
        user = types.SimpleNamespace(pw_name="alice", pw_dir="/home/alice")

        with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "ttl_invalid"):
            daemon.issue_bootstrap(1000, user, {"ttlSeconds": True})

    def test_issue_rejects_invalid_reason_before_issuer_call(self) -> None:
        daemon = self.daemon()
        user = types.SimpleNamespace(pw_name="alice", pw_dir="/home/alice")
        original_yq_read = bastion_bootstrapd.yq_read
        bastion_bootstrapd.yq_read = lambda _path: "600"
        try:
            with self.assertRaisesRegex(bastion_bootstrapd.DaemonError, "reason_invalid"):
                daemon.issue_bootstrap(1000, user, {"reason": "bad", "ttlSeconds": 60})
        finally:
            bastion_bootstrapd.yq_read = original_yq_read


if __name__ == "__main__":
    unittest.main()
