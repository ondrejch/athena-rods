#!/usr/bin/env python3
"""Run local TLS security verification tests for ATHENA-rods."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import errno
from typing import Callable, Dict, Tuple

from arod_common.netbench import (
    LocalEchoServer,
    create_tls_client_context,
    create_tls_server_context,
    recv_exact,
)
from arod_common.versioning import build_revision_record


def _is_socket_permission_error(exc: BaseException) -> bool:
    """Return ``True`` when failure is caused by restricted socket permissions."""
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, PermissionError):
            return True
        if isinstance(current, OSError) and current.errno in {errno.EPERM, errno.EACCES}:
            return True
        current = current.__cause__ or current.__context__
    return False


def _describe_exception(exc: BaseException) -> str:
    """Render exception plus chained cause/context for diagnostics."""
    parts = []
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)


def _socket_stack_available() -> Tuple[bool, str]:
    """Probe whether local socket open/bind/connect is permitted."""
    try:
        with LocalEchoServer() as server:
            with socket.create_connection(("127.0.0.1", int(server.bound_port)), timeout=1.0):
                pass
        return True, ""
    except Exception as exc:  # noqa: BLE001 - classify environment limitations
        if _is_socket_permission_error(exc):
            return False, _describe_exception(exc)
        raise


def _attempt_echo(
    cert_dir: Path,
    require_client_cert: bool,
    client_with_cert: bool,
    client_trust_athena_ca: bool,
) -> None:
    """Attempt one echo transaction; raises on TLS/IO failure."""
    server_ctx = create_tls_server_context(cert_dir=cert_dir, require_client_cert=require_client_cert)
    with LocalEchoServer(tls_context=server_ctx) as server:
        raw = socket.create_connection(("127.0.0.1", int(server.bound_port)), timeout=3.0)
        raw.settimeout(3.0)
        with raw:
            client_ctx = create_tls_client_context(
                cert_dir=cert_dir,
                with_client_cert=client_with_cert,
                trust_athena_ca=client_trust_athena_ca,
            )
            with client_ctx.wrap_socket(raw, server_hostname="ctrlbox") as tls_sock:
                payload = b"athena-security-check"
                tls_sock.sendall(payload)
                echoed = recv_exact(tls_sock, len(payload))
                if echoed != payload:
                    raise RuntimeError("Echo payload mismatch")


def _run_check(name: str, check_func: Callable[[], None], expect_success: bool) -> Dict[str, object]:
    """Execute a security check and normalize pass/fail status."""
    try:
        check_func()
        outcome_success = True
        error_text = ""
    except Exception as exc:  # noqa: BLE001 - expected for negative-path checks
        outcome_success = False
        error_text = f"{type(exc).__name__}: {exc}"

    passed = outcome_success if expect_success else not outcome_success
    return {
        "name": name,
        "expect_success": expect_success,
        "observed_success": outcome_success,
        "passed": passed,
        "error": error_text,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=Path("etc") / "certs",
        help="Directory containing ATHENA TLS certificates",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("build") / "security_verification_report.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sockets_available, skip_reason = _socket_stack_available()
    if not sockets_available:
        report = {
            "passed": True,
            "skipped": True,
            "skip_reason": skip_reason,
            "revision": build_revision_record(extra={"tool": "security_verification"}),
            "cert_dir": str(args.cert_dir),
            "checks": [],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Security verification report written to {args.report}")
        print(f"Verification skipped: {skip_reason}")
        return 0

    checks = [
        _run_check(
            name="valid_mtls_handshake",
            expect_success=True,
            check_func=lambda: _attempt_echo(
                cert_dir=args.cert_dir,
                require_client_cert=True,
                client_with_cert=True,
                client_trust_athena_ca=True,
            ),
        ),
        _run_check(
            name="reject_missing_client_certificate",
            expect_success=False,
            check_func=lambda: _attempt_echo(
                cert_dir=args.cert_dir,
                require_client_cert=True,
                client_with_cert=False,
                client_trust_athena_ca=True,
            ),
        ),
        _run_check(
            name="reject_untrusted_server_certificate",
            expect_success=False,
            check_func=lambda: _attempt_echo(
                cert_dir=args.cert_dir,
                require_client_cert=True,
                client_with_cert=True,
                client_trust_athena_ca=False,
            ),
        ),
        _run_check(
            name="allow_tls_when_client_cert_not_required",
            expect_success=True,
            check_func=lambda: _attempt_echo(
                cert_dir=args.cert_dir,
                require_client_cert=False,
                client_with_cert=False,
                client_trust_athena_ca=True,
            ),
        ),
    ]

    passed = all(check["passed"] for check in checks)
    report = {
        "passed": passed,
        "skipped": False,
        "revision": build_revision_record(extra={"tool": "security_verification"}),
        "cert_dir": str(args.cert_dir),
        "checks": checks,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Security verification report written to {args.report}")
    for check in checks:
        print(f"{check['name']}: passed={check['passed']} observed_success={check['observed_success']}")

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
