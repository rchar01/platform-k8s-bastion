#!/usr/bin/env python3
"""Safely install kubeconfig files under managed user home directories."""

from __future__ import annotations

import argparse
import os
import pwd
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


class WriterError(Exception):
    pass


@dataclass(frozen=True)
class TargetUser:
    name: str
    uid: int
    gid: int


def _safe_fchown(fd: int, uid: int, gid: int) -> None:
    try:
        os.fchown(fd, uid, gid)
    except PermissionError:
        if os.geteuid() == uid:
            return
        raise


def _validate_destination_name(name: str) -> None:
    if name not in {"bootstrap", "config"}:
        raise WriterError(f"unsupported destination: {name}")


def _open_kube_dir(user: TargetUser, home_dir: str, *, allow_non_home: bool = False) -> tuple[int, int]:
    home = Path(home_dir)
    if not allow_non_home and not str(home).startswith("/home/"):
        raise WriterError(f"home_not_allowed: {home_dir}")

    try:
        home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError as exc:
        raise WriterError(f"home_not_found: {home_dir}") from exc
    except OSError as exc:
        raise WriterError(f"home_not_safe: {home_dir}") from exc

    kube_fd: int | None = None
    try:
        home_stat = os.fstat(home_fd)
        if not stat.S_ISDIR(home_stat.st_mode):
            raise WriterError(f"home_not_directory: {home_dir}")
        if home_stat.st_uid != user.uid:
            raise WriterError(f"home_owner_mismatch: {home_dir}")

        try:
            os.mkdir(".kube", mode=0o700, dir_fd=home_fd)
        except FileExistsError:
            pass

        try:
            kube_fd = os.open(".kube", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
        except OSError as exc:
            raise WriterError(f"kube_dir_not_safe: {home_dir}/.kube") from exc

        kube_stat = os.fstat(kube_fd)
        if not stat.S_ISDIR(kube_stat.st_mode):
            raise WriterError(f"kube_dir_not_directory: {home_dir}/.kube")
        if kube_stat.st_uid not in (0, user.uid):
            raise WriterError(f"kube_dir_owner_mismatch: {home_dir}/.kube")

        _safe_fchown(kube_fd, user.uid, user.gid)
        os.fchmod(kube_fd, 0o700)
        return home_fd, kube_fd
    except Exception:
        if kube_fd is not None:
            os.close(kube_fd)
        os.close(home_fd)
        raise


def _existing_file_bytes(kube_fd: int, name: str) -> bytes | None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=kube_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise WriterError(f"destination_not_safe: {name}") from exc

    with os.fdopen(fd, "rb") as fp:
        existing_stat = os.fstat(fp.fileno())
        if not stat.S_ISREG(existing_stat.st_mode):
            raise WriterError(f"destination_not_regular: {name}")
        return fp.read()


def _chmod_chown_existing(kube_fd: int, name: str, user: TargetUser) -> None:
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=kube_fd)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise WriterError(f"destination_not_safe: {name}") from exc

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise WriterError(f"destination_not_regular: {name}")
        _safe_fchown(fd, user.uid, user.gid)
        os.fchmod(fd, 0o600)
        os.fsync(fd)
    finally:
        os.close(fd)


def remove_user_kube_file(user: TargetUser, home_dir: str, name: str, *, allow_non_home: bool = False) -> bool:
    _validate_destination_name(name)
    home_fd, kube_fd = _open_kube_dir(user, home_dir, allow_non_home=allow_non_home)
    try:
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=kube_fd)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise WriterError(f"destination_not_safe: {name}") from exc

        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise WriterError(f"destination_not_regular: {name}")
        finally:
            os.close(fd)

        os.unlink(name, dir_fd=kube_fd)
        os.fsync(kube_fd)
        return True
    finally:
        os.close(kube_fd)
        os.close(home_fd)


def install_user_kube_file(user: TargetUser, home_dir: str, name: str, content: bytes, *, allow_non_home: bool = False) -> bool:
    _validate_destination_name(name)
    if not content.endswith(b"\n"):
        content += b"\n"

    home_fd, kube_fd = _open_kube_dir(user, home_dir, allow_non_home=allow_non_home)
    fd: int | None = None
    tmp_name = ""
    try:
        existing = _existing_file_bytes(kube_fd, name)
        if existing == content:
            _chmod_chown_existing(kube_fd, name, user)
            return False

        tmp_name = f".{name}.{uuid.uuid4().hex}.tmp"
        fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=kube_fd)
        _safe_fchown(fd, user.uid, user.gid)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as fp:
            fd = None
            fp.write(content)
            fp.flush()
            os.fsync(fp.fileno())

        os.replace(tmp_name, name, src_dir_fd=kube_fd, dst_dir_fd=kube_fd)
        tmp_name = ""
        _chmod_chown_existing(kube_fd, name, user)
        os.fsync(kube_fd)
        return True
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_name:
            try:
                os.unlink(tmp_name, dir_fd=kube_fd)
            except FileNotFoundError:
                pass
        os.close(kube_fd)
        os.close(home_fd)


def _target_user(name: str) -> TargetUser:
    try:
        entry = pwd.getpwnam(name)
    except KeyError as exc:
        raise WriterError(f"user_not_found: {name}") from exc
    return TargetUser(name=entry.pw_name, uid=entry.pw_uid, gid=entry.pw_gid)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely install a user kubeconfig")
    parser.add_argument("--user", required=True)
    parser.add_argument("--home-dir", required=True)
    parser.add_argument("--dest", required=True, choices=("bootstrap", "config"))
    parser.add_argument("--source")
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--remove", action="append", default=[])
    args = parser.parse_args(argv)

    if not args.remove and bool(args.source) == bool(args.stdin):
        parser.error("exactly one of --source or --stdin is required")
    if args.remove and args.source and args.stdin:
        parser.error("--source and --stdin are mutually exclusive")

    try:
        user = _target_user(args.user)
        for name in args.remove:
            if remove_user_kube_file(user, args.home_dir, name):
                print(f"removed {name}")

        if args.remove and not args.source and not args.stdin:
            return 0

        if args.stdin:
            content = sys.stdin.buffer.read()
        else:
            content = Path(args.source).read_bytes()

        changed = install_user_kube_file(user, args.home_dir, args.dest, content)
        print(f"{'changed' if changed else 'unchanged'} {args.dest}")
        return 0
    except WriterError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
