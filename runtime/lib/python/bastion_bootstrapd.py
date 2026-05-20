#!/usr/bin/env python3
"""Root-owned local daemon for login bootstrap operations."""

from __future__ import annotations

import datetime as dt
import errno
import json
import os
import pwd
import grp
import shutil
import signal
import socket
import stat
import struct
import subprocess
import tempfile
import threading
import traceback
import uuid
from pathlib import Path
from typing import Any


PROGRAM_NAME = "bastion-bootstrapd"
POLICY_PATH = os.environ.get("POLICY_FILE", "/etc/bastion/access-policy.yaml")
DEFAULT_SOCKET_PATH = "/run/bastion-bootstrapd/bootstrapd.sock"
RUNTIME_DIR = Path("/run/bastion-bootstrapd")
RUNTIME_TOKENS_DIR = "/run/bastion-bootstrapd/tokens"
RUNTIME_FAILURES_DIR = "/run/bastion-bootstrapd/failures"
ALLOWED_ACTIONS = {"health", "issue-bootstrap", "revoke-bootstrap"}
MAX_CONCURRENT_CONNECTIONS = 32


class DaemonError(Exception):
    pass


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso8601(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def run_cmd(cmd: list[str], timeout_seconds: int) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired as exc:
        raise DaemonError("command_timeout") from exc
    if proc.returncode != 0:
        raise DaemonError(f"command_failed rc={proc.returncode}")
    return proc.stdout


def yq_read(path: str) -> str:
    out = run_cmd(["yq", "-r", path, POLICY_PATH], timeout_seconds=10)
    return out.strip()


def log_event(level: str, action: str, result: str, request_id: str, uid: int | None, username: str | None, details: dict[str, Any] | None = None) -> None:
    payload = {
        "ts": iso_now(),
        "program": PROGRAM_NAME,
        "hostname": socket.gethostname(),
        "level": level,
        "action": action,
        "result": result,
        "requestId": request_id,
        "uid": uid,
        "username": username,
        "details": details or {},
    }
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_json_file(path: Path, data: dict[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".tmp.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(data, fp, separators=(",", ":"))
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        os.chmod(path, mode)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def normalize_socket_path(raw_path: str, base_dir: Path = RUNTIME_DIR) -> str:
    if not raw_path:
        raise DaemonError("daemon.socket.path missing in policy")

    path = Path(os.path.normpath(raw_path))
    if not path.is_absolute():
        raise DaemonError("daemon.socket.path must be absolute")
    try:
        path.relative_to(base_dir)
    except ValueError as exc:
        raise DaemonError(f"daemon.socket.path must be under {base_dir}") from exc
    if path.parent != base_dir:
        raise DaemonError(f"daemon.socket.path must be a direct child of {base_dir}")
    if not path.name or path.name in {".", ".."}:
        raise DaemonError("daemon.socket.path must include a socket filename")
    return str(path)


class BootstrapDaemon:
    def __init__(self) -> None:
        self.allowed_group = yq_read('.daemon.allowedLoginGroup // ""')
        self.socket_path = normalize_socket_path(yq_read('.daemon.socket.path // ""') or DEFAULT_SOCKET_PATH)
        self.max_bytes = int(yq_read('.daemon.request.maxBytes // "0"'))
        self.request_timeout = int(yq_read('.daemon.request.timeoutSeconds // "0"'))
        self.failure_backoff = int(yq_read('.daemon.rateLimit.failureBackoffSeconds // "0"'))

        if not self.allowed_group:
            raise DaemonError("daemon.allowedLoginGroup missing in policy")
        if self.max_bytes <= 0:
            raise DaemonError("daemon.request.maxBytes must be > 0")
        if self.request_timeout <= 0:
            raise DaemonError("daemon.request.timeoutSeconds must be > 0")
        if self.failure_backoff <= 0:
            raise DaemonError("daemon.rateLimit.failureBackoffSeconds must be > 0")

        self.shutdown_event = threading.Event()
        self.inflight_locks: dict[int, threading.Lock] = {}
        self.inflight_global_lock = threading.Lock()
        self.connection_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_CONNECTIONS)

    def token_cache_path(self, uid: int) -> Path:
        return Path(RUNTIME_TOKENS_DIR) / f"{uid}.json"

    def failure_cache_path(self, uid: int) -> Path:
        return Path(RUNTIME_FAILURES_DIR) / f"{uid}.json"

    def inflight_lock_for_uid(self, uid: int) -> threading.Lock:
        with self.inflight_global_lock:
            return self.inflight_locks.setdefault(uid, threading.Lock())

    def peer_identity(self, conn: socket.socket) -> tuple[int, int, int]:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", raw)
        return uid, gid, pid

    def load_user(self, uid: int) -> pwd.struct_passwd:
        try:
            return pwd.getpwuid(uid)
        except KeyError as exc:
            raise DaemonError("uid_not_found") from exc

    def user_in_group(self, user: pwd.struct_passwd, group_name: str) -> bool:
        try:
            grp_entry = grp.getgrnam(group_name)
        except KeyError:
            return False

        if user.pw_gid == grp_entry.gr_gid:
            return True
        return user.pw_name in grp_entry.gr_mem

    def authorize(self, action: str, uid: int, user: pwd.struct_passwd) -> None:
        if action not in ALLOWED_ACTIONS:
            raise DaemonError("action_not_allowed")
        if uid == 0 or uid < 1000:
            raise DaemonError("uid_not_allowed")
        if user.pw_shell in ("/usr/sbin/nologin", "/sbin/nologin", "/bin/false"):
            raise DaemonError("account_disabled")
        if not user.pw_dir.startswith("/home/"):
            raise DaemonError("home_not_allowed")
        if not self.user_in_group(user, self.allowed_group):
            raise DaemonError("group_denied")

    def ensure_runtime_paths(self) -> None:
        run_dir = Path(self.socket_path).parent
        if run_dir != RUNTIME_DIR:
            raise DaemonError(f"daemon.socket.path must be a direct child of {RUNTIME_DIR}")
        if run_dir.is_symlink():
            raise DaemonError(f"runtime directory is a symlink: {run_dir}")
        run_dir.mkdir(parents=True, exist_ok=True)

        try:
            gid = grp.getgrnam(self.allowed_group).gr_gid
        except KeyError:
            raise DaemonError(f"allowed group not found: {self.allowed_group}")

        try:
            run_fd = os.open(run_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise DaemonError(f"runtime directory is not safe: {run_dir}") from exc
        try:
            os.fchown(run_fd, 0, gid)
            os.fchmod(run_fd, 0o750)
        finally:
            os.close(run_fd)

        Path(RUNTIME_TOKENS_DIR).mkdir(parents=True, exist_ok=True)
        os.chmod(RUNTIME_TOKENS_DIR, 0o700)
        Path(RUNTIME_FAILURES_DIR).mkdir(parents=True, exist_ok=True)
        os.chmod(RUNTIME_FAILURES_DIR, 0o700)

    def remove_stale_socket(self) -> None:
        try:
            socket_stat = os.lstat(self.socket_path)
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(socket_stat.st_mode):
            raise DaemonError(f"refusing to unlink non-socket path: {self.socket_path}")
        if socket_stat.st_uid != 0:
            raise DaemonError(f"refusing to unlink non-root-owned socket: {self.socket_path}")
        os.unlink(self.socket_path)

    def should_backoff(self, uid: int) -> bool:
        cache = read_json_file(self.failure_cache_path(uid))
        if not cache:
            return False
        last_failed = cache.get("lastFailureEpoch", 0)
        if not isinstance(last_failed, int):
            return False
        return (int(dt.datetime.now().timestamp()) - last_failed) < self.failure_backoff

    def write_failure(self, uid: int, reason: str) -> None:
        write_json_file(
            self.failure_cache_path(uid),
            {
                "uid": uid,
                "lastFailureEpoch": int(dt.datetime.now().timestamp()),
                "lastFailureAt": iso_now(),
                "reason": reason,
            },
        )

    def clear_failure(self, uid: int) -> None:
        path = self.failure_cache_path(uid)
        if path.exists():
            path.unlink(missing_ok=True)

    def revoke_token_best_effort(self, token_id: str) -> None:
        if not token_id:
            return
        try:
            run_cmd(
                [
                    "/usr/local/sbin/bastion-bootstrap-token-revoke",
                    "--token-id",
                    token_id,
                    "--best-effort",
                ],
                timeout_seconds=self.request_timeout,
            )
        except Exception:
            pass

    def write_bootstrap_file(self, user: pwd.struct_passwd, kubeconfig: str) -> str:
        home = Path(user.pw_dir)
        home_fd: int | None = None
        kube_fd: int | None = None
        fd: int | None = None
        tmp_name = ""

        if not str(home).startswith("/home/"):
            raise DaemonError("home_not_allowed")

        try:
            home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError as exc:
            raise DaemonError("home_not_found") from exc
        except OSError as exc:
            raise DaemonError("home_not_safe") from exc

        try:
            home_stat = os.fstat(home_fd)
            if not stat.S_ISDIR(home_stat.st_mode):
                raise DaemonError("home_not_directory")
            if home_stat.st_uid != user.pw_uid:
                raise DaemonError("home_owner_mismatch")

            try:
                os.mkdir(".kube", mode=0o700, dir_fd=home_fd)
            except FileExistsError:
                pass

            try:
                kube_fd = os.open(".kube", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
            except OSError as exc:
                raise DaemonError("kube_dir_not_safe") from exc

            kube_stat = os.fstat(kube_fd)
            if not stat.S_ISDIR(kube_stat.st_mode):
                raise DaemonError("kube_dir_not_directory")
            if kube_stat.st_uid not in (0, user.pw_uid):
                raise DaemonError("kube_dir_owner_mismatch")

            os.fchown(kube_fd, user.pw_uid, user.pw_gid)
            os.fchmod(kube_fd, 0o700)

            tmp_name = f".bootstrap.{uuid.uuid4().hex}.tmp"
            fd = os.open(tmp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=kube_fd)
            os.fchown(fd, user.pw_uid, user.pw_gid)
            os.fchmod(fd, 0o600)

            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                fd = None
                fp.write(kubeconfig)
                if not kubeconfig.endswith("\n"):
                    fp.write("\n")
                fp.flush()
                os.fsync(fp.fileno())

            os.replace(tmp_name, "bootstrap", src_dir_fd=kube_fd, dst_dir_fd=kube_fd)
            tmp_name = ""
            os.fsync(kube_fd)
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if tmp_name and kube_fd is not None:
                try:
                    os.unlink(tmp_name, dir_fd=kube_fd)
                except FileNotFoundError:
                    pass
            if kube_fd is not None:
                os.close(kube_fd)
            if home_fd is not None:
                os.close(home_fd)

        return str(home / ".kube/bootstrap")

    def remove_bootstrap_file(self, user: pwd.struct_passwd) -> None:
        home = Path(user.pw_dir)
        home_fd: int | None = None
        kube_fd: int | None = None
        fd: int | None = None

        if not str(home).startswith("/home/"):
            raise DaemonError("home_not_allowed")

        try:
            home_fd = os.open(home, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise DaemonError("home_not_safe") from exc

        try:
            home_stat = os.fstat(home_fd)
            if not stat.S_ISDIR(home_stat.st_mode):
                raise DaemonError("home_not_directory")
            if home_stat.st_uid != user.pw_uid:
                raise DaemonError("home_owner_mismatch")

            try:
                kube_fd = os.open(".kube", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=home_fd)
            except FileNotFoundError:
                return
            except OSError as exc:
                raise DaemonError("kube_dir_not_safe") from exc

            kube_stat = os.fstat(kube_fd)
            if not stat.S_ISDIR(kube_stat.st_mode):
                raise DaemonError("kube_dir_not_directory")
            if kube_stat.st_uid not in (0, user.pw_uid):
                raise DaemonError("kube_dir_owner_mismatch")

            try:
                fd = os.open("bootstrap", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=kube_fd)
            except FileNotFoundError:
                return
            except OSError as exc:
                raise DaemonError("bootstrap_not_safe") from exc

            file_stat = os.fstat(fd)
            if not stat.S_ISREG(file_stat.st_mode):
                raise DaemonError("bootstrap_not_regular")

            os.close(fd)
            fd = None
            os.unlink("bootstrap", dir_fd=kube_fd)
            os.fsync(kube_fd)
        finally:
            if fd is not None:
                os.close(fd)
            if kube_fd is not None:
                os.close(kube_fd)
            if home_fd is not None:
                os.close(home_fd)

    def issue_bootstrap(self, uid: int, user: pwd.struct_passwd, payload: dict[str, Any]) -> dict[str, Any]:
        reason = str(payload.get("reason") or "login-recovery")
        ttl_seconds = payload.get("ttlSeconds")
        if ttl_seconds is None:
            ttl_seconds = int(yq_read('.bootstrap.ttl.defaultSeconds // "0"'))
        if not isinstance(ttl_seconds, int) or isinstance(ttl_seconds, bool):
            raise DaemonError("ttl_invalid")
        if ttl_seconds < 60:
            raise DaemonError("ttl_too_small")
        max_ttl_seconds = int(yq_read('.bootstrap.ttl.maxSeconds // "0"'))
        if max_ttl_seconds <= 0:
            raise DaemonError("ttl_max_invalid")
        if ttl_seconds > max_ttl_seconds:
            raise DaemonError("ttl_too_large")
        if reason not in {"initial-enrollment", "login-recovery", "manual-recovery"}:
            raise DaemonError("reason_invalid")

        cache = read_json_file(self.token_cache_path(uid))
        if cache:
            expires_at = parse_iso8601(str(cache.get("expiresAt", "")))
            cache_token_id = str(cache.get("tokenId") or "")
            if expires_at and expires_at > dt.datetime.now(dt.timezone.utc):
                bootstrap_path = Path(user.pw_dir) / ".kube/bootstrap"
                if bootstrap_path.is_file():
                    return {
                        "user": user.pw_name,
                        "tokenId": cache.get("tokenId", ""),
                        "expiresAt": cache.get("expiresAt", ""),
                        "bootstrapKubeconfigPath": str(bootstrap_path),
                        "reused": True,
                    }

                if cache_token_id:
                    run_cmd(
                        [
                            "/usr/local/sbin/bastion-bootstrap-token-revoke",
                            "--token-id",
                            cache_token_id,
                        ],
                        timeout_seconds=self.request_timeout,
                    )

                self.token_cache_path(uid).unlink(missing_ok=True)
            else:
                self.token_cache_path(uid).unlink(missing_ok=True)

        cmd = [
            "/usr/local/sbin/bastion-bootstrap-token-issue",
            "--user",
            user.pw_name,
            "--reason",
            reason,
            "--ttl-seconds",
            str(ttl_seconds),
            "--json",
        ]
        stdout = run_cmd(cmd, timeout_seconds=self.request_timeout)
        issue = json.loads(stdout)

        token_id = str(issue.get("tokenId") or "")
        expires_at = str(issue.get("expiresAt") or "")
        bootstrap_kubeconfig = str(issue.get("bootstrapKubeconfig") or "")

        if not token_id:
            raise DaemonError("issuer_missing_token_id")
        if not expires_at:
            raise DaemonError("issuer_missing_expires_at")
        if not bootstrap_kubeconfig:
            raise DaemonError("issuer_missing_bootstrap_kubeconfig")

        try:
            bootstrap_path = self.write_bootstrap_file(user, bootstrap_kubeconfig)
            write_json_file(
                self.token_cache_path(uid),
                {
                    "user": user.pw_name,
                    "uid": uid,
                    "tokenId": token_id,
                    "issuedAt": iso_now(),
                    "expiresAt": expires_at,
                    "reason": reason,
                },
            )
        except Exception:
            self.revoke_token_best_effort(token_id)
            raise
        self.clear_failure(uid)

        return {
            "user": user.pw_name,
            "tokenId": token_id,
            "expiresAt": expires_at,
            "bootstrapKubeconfigPath": bootstrap_path,
            "reused": False,
        }

    def revoke_bootstrap(self, uid: int, _user: pwd.struct_passwd, payload: dict[str, Any]) -> dict[str, Any]:
        cache = read_json_file(self.token_cache_path(uid)) or {}
        token_id = str(payload.get("tokenId") or cache.get("tokenId") or "")
        if not token_id:
            raise DaemonError("token_id_required")

        cached_token_id = str(cache.get("tokenId") or "")
        if cached_token_id and token_id != cached_token_id:
            raise DaemonError("token_not_owned_by_uid")

        cmd = ["/usr/local/sbin/bastion-bootstrap-token-revoke", "--token-id", token_id]
        run_cmd(cmd, timeout_seconds=self.request_timeout)
        self.token_cache_path(uid).unlink(missing_ok=True)
        try:
            self.remove_bootstrap_file(_user)
        except DaemonError:
            pass
        return {"revoked": True, "tokenId": token_id}

    def dispatch(self, action: str, uid: int, user: pwd.struct_passwd, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "health":
            return {"status": "ok"}
        if action == "issue-bootstrap":
            if self.should_backoff(uid):
                raise DaemonError("rate_limited")

            lock = self.inflight_lock_for_uid(uid)

            if not lock.acquire(blocking=False):
                raise DaemonError("busy")

            try:
                return self.issue_bootstrap(uid, user, payload)
            except Exception as exc:
                self.write_failure(uid, str(exc))
                raise
            finally:
                lock.release()
        if action == "revoke-bootstrap":
            lock = self.inflight_lock_for_uid(uid)
            if not lock.acquire(blocking=False):
                raise DaemonError("busy")
            try:
                return self.revoke_bootstrap(uid, user, payload)
            finally:
                lock.release()
        raise DaemonError("action_not_allowed")

    def decode_request(self, conn: socket.socket) -> dict[str, Any]:
        conn.settimeout(self.request_timeout)
        chunks: list[bytes] = []
        total = 0

        while True:
            data = conn.recv(4096)
            if not data:
                break
            chunks.append(data)
            total += len(data)
            if total > self.max_bytes:
                raise DaemonError("request_too_large")

        raw = b"".join(chunks).decode("utf-8", errors="strict").strip()
        if not raw:
            raise DaemonError("empty_request")

        req = json.loads(raw)
        if not isinstance(req, dict):
            raise DaemonError("request_not_object")

        version = req.get("version")
        if version != 1:
            raise DaemonError("unsupported_version")

        action = req.get("action")
        if action not in ALLOWED_ACTIONS:
            raise DaemonError("unknown_action")

        payload = req.get("payload")
        if payload is None:
            req["payload"] = {}
        elif not isinstance(payload, dict):
            raise DaemonError("payload_not_object")

        if not req.get("requestId"):
            req["requestId"] = str(uuid.uuid4())

        return req

    def send_response(self, conn: socket.socket, request_id: str, ok: bool, result: dict[str, Any] | None, error: str | None) -> None:
        body = {
            "ok": ok,
            "requestId": request_id,
            "result": result if result is not None else {},
            "error": error,
        }
        payload = (json.dumps(body, separators=(",", ":")) + "\n").encode("utf-8")
        conn.sendall(payload)

    def handle_connection(self, conn: socket.socket) -> None:
        request_id = str(uuid.uuid4())
        uid: int | None = None
        username: str | None = None
        action = "unknown"
        try:
            uid, _gid, _pid = self.peer_identity(conn)
            user = self.load_user(uid)
            username = user.pw_name

            req = self.decode_request(conn)
            request_id = str(req.get("requestId") or request_id)
            action = str(req.get("action"))
            payload = req.get("payload") or {}

            self.authorize(action, uid, user)
            result = self.dispatch(action, uid, user, payload)
            self.send_response(conn, request_id, True, result, None)

            token_id = str(result.get("tokenId") or "")
            details = {"tokenIdRedacted": True} if token_id else {}
            log_event("info", action, "ok", request_id, uid, username, details)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_response(conn, request_id, False, None, "malformed_request")
            log_event("warn", action, "error", request_id, uid, username, {"error": "malformed_request"})
        except (DaemonError, subprocess.TimeoutExpired) as exc:
            self.send_response(conn, request_id, False, None, str(exc))
            log_event("warn", action, "error", request_id, uid, username, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover
            self.send_response(conn, request_id, False, None, "internal_error")
            log_event(
                "error",
                action,
                "error",
                request_id,
                uid,
                username,
                {
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=2),
                },
            )
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def handle_connection_limited(self, conn: socket.socket) -> None:
        try:
            self.handle_connection(conn)
        finally:
            self.connection_semaphore.release()

    def serve_forever(self) -> None:
        self.ensure_runtime_paths()
        self.remove_stale_socket()

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(self.socket_path)
        sock.listen(128)
        sock.settimeout(1.0)

        try:
            gid = grp.getgrnam(self.allowed_group).gr_gid
            os.chown(self.socket_path, 0, gid)
            os.chmod(self.socket_path, 0o660)
        except KeyError as exc:
            raise DaemonError(f"allowed group not found: {self.allowed_group}") from exc

        log_event("info", "daemon", "started", str(uuid.uuid4()), 0, "root", {"socket": self.socket_path})

        try:
            while not self.shutdown_event.is_set():
                try:
                    conn, _addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if exc.errno == errno.EINTR:
                        continue
                    raise
                if not self.connection_semaphore.acquire(blocking=False):
                    request_id = str(uuid.uuid4())
                    try:
                        self.send_response(conn, request_id, False, None, "server_busy")
                    except OSError:
                        pass
                    try:
                        conn.close()
                    except OSError:
                        pass
                    log_event("warn", "connection", "error", request_id, None, None, {"error": "server_busy"})
                    continue

                try:
                    thread = threading.Thread(target=self.handle_connection_limited, args=(conn,), daemon=True)
                    thread.start()
                except Exception as exc:
                    self.connection_semaphore.release()
                    try:
                        conn.close()
                    except OSError:
                        pass
                    log_event("error", "connection", "error", str(uuid.uuid4()), None, None, {"error": "thread_start_failed", "detail": str(exc)})
        finally:
            sock.close()
            try:
                os.unlink(self.socket_path)
            except FileNotFoundError:
                pass
            log_event("info", "daemon", "stopped", str(uuid.uuid4()), 0, "root")


def main() -> None:
    if os.geteuid() != 0:
        raise SystemExit("Run as root")
    if shutil.which("yq") is None:
        raise SystemExit("Missing command: yq")

    daemon = BootstrapDaemon()

    def shutdown_handler(signum: int, _frame: Any) -> None:
        _ = signum
        daemon.shutdown_event.set()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    daemon.serve_forever()


if __name__ == "__main__":
    main()
