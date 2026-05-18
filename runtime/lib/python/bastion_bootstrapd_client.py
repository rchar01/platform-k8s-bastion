#!/usr/bin/env python3
"""Client for bastion-bootstrapd Unix socket API."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import uuid
from typing import Any


DEFAULT_SOCKET = "/run/bastion-bootstrapd/bootstrapd.sock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bastion-bootstrapd-client",
        description="Send a request to bastion-bootstrapd",
    )
    parser.add_argument("action", choices=["health", "issue-bootstrap", "revoke-bootstrap"])
    parser.add_argument("--socket", default=DEFAULT_SOCKET, dest="socket_path")
    parser.add_argument("--timeout-seconds", type=int, default=10)
    parser.add_argument("--request-id", default="")
    parser.add_argument("--reason", default="login-recovery")
    parser.add_argument("--ttl-seconds", type=int)
    parser.add_argument("--token-id", default="")
    return parser.parse_args()


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if args.action == "issue-bootstrap":
        payload["reason"] = args.reason
        if args.ttl_seconds is not None:
            payload["ttlSeconds"] = args.ttl_seconds
    elif args.action == "revoke-bootstrap":
        if args.token_id:
            payload["tokenId"] = args.token_id
    return payload


def send_request(args: argparse.Namespace) -> dict[str, Any]:
    request = {
        "version": 1,
        "action": args.action,
        "requestId": args.request_id or str(uuid.uuid4()),
        "payload": build_payload(args),
    }

    raw_request = (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(args.timeout_seconds)
        conn.connect(args.socket_path)
        conn.sendall(raw_request)
        conn.shutdown(socket.SHUT_WR)

        chunks: list[bytes] = []
        while True:
            data = conn.recv(4096)
            if not data:
                break
            chunks.append(data)

    response = b"".join(chunks).decode("utf-8", errors="strict").strip()
    if not response:
        raise RuntimeError("empty_response")
    return json.loads(response)


def main() -> int:
    args = parse_args()
    try:
        response = send_request(args)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(response, separators=(",", ":")))
    if response.get("ok") is True:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
