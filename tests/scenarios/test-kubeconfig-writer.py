#!/usr/bin/env python3
"""Unit tests for safe kubeconfig file installation."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest


ROOT_DIR = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT_DIR / "runtime/lib/python/bastion_kubeconfig_writer.py"

spec = importlib.util.spec_from_file_location("bastion_kubeconfig_writer", MODULE_PATH)
assert spec is not None and spec.loader is not None
bastion_kubeconfig_writer = importlib.util.module_from_spec(spec)
sys.modules["bastion_kubeconfig_writer"] = bastion_kubeconfig_writer
spec.loader.exec_module(bastion_kubeconfig_writer)


class KubeconfigWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = pathlib.Path(self.tmp.name) / "alice"
        self.home.mkdir(mode=0o700)
        self.user = bastion_kubeconfig_writer.TargetUser(
            name="alice",
            uid=os.getuid(),
            gid=os.getgid(),
        )

    def test_install_creates_private_kubeconfig(self) -> None:
        changed = bastion_kubeconfig_writer.install_user_kube_file(
            self.user,
            str(self.home),
            "bootstrap",
            b"apiVersion: v1",
            allow_non_home=True,
        )

        target = self.home / ".kube/bootstrap"
        self.assertTrue(changed)
        self.assertEqual(target.read_text(encoding="utf-8"), "apiVersion: v1\n")
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)

    def test_install_unchanged_returns_false(self) -> None:
        bastion_kubeconfig_writer.install_user_kube_file(
            self.user,
            str(self.home),
            "config",
            b"apiVersion: v1",
            allow_non_home=True,
        )

        changed = bastion_kubeconfig_writer.install_user_kube_file(
            self.user,
            str(self.home),
            "config",
            b"apiVersion: v1\n",
            allow_non_home=True,
        )

        self.assertFalse(changed)

    def test_refuses_symlinked_kube_directory(self) -> None:
        (self.home / ".kube-target").mkdir()
        (self.home / ".kube").symlink_to(self.home / ".kube-target")

        with self.assertRaisesRegex(bastion_kubeconfig_writer.WriterError, "kube_dir_not_safe"):
            bastion_kubeconfig_writer.install_user_kube_file(
                self.user,
                str(self.home),
                "bootstrap",
                b"apiVersion: v1",
                allow_non_home=True,
            )

    def test_refuses_symlinked_target(self) -> None:
        kube_dir = self.home / ".kube"
        kube_dir.mkdir(mode=0o700)
        (self.home / "target").write_text("owned\n", encoding="utf-8")
        (kube_dir / "config").symlink_to(self.home / "target")

        with self.assertRaisesRegex(bastion_kubeconfig_writer.WriterError, "destination_not_safe"):
            bastion_kubeconfig_writer.install_user_kube_file(
                self.user,
                str(self.home),
                "config",
                b"apiVersion: v1",
                allow_non_home=True,
            )

        self.assertEqual((self.home / "target").read_text(encoding="utf-8"), "owned\n")

    def test_remove_refuses_symlinked_target(self) -> None:
        kube_dir = self.home / ".kube"
        kube_dir.mkdir(mode=0o700)
        (self.home / "target").write_text("owned\n", encoding="utf-8")
        (kube_dir / "bootstrap").symlink_to(self.home / "target")

        with self.assertRaisesRegex(bastion_kubeconfig_writer.WriterError, "destination_not_safe"):
            bastion_kubeconfig_writer.remove_user_kube_file(
                self.user,
                str(self.home),
                "bootstrap",
                allow_non_home=True,
            )

        self.assertTrue((kube_dir / "bootstrap").is_symlink())
        self.assertEqual((self.home / "target").read_text(encoding="utf-8"), "owned\n")


if __name__ == "__main__":
    unittest.main()
