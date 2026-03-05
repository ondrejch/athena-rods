#!/usr/bin/env python3
"""Benchmark local TCP vs mTLS network performance for ATHENA-rods."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import socket
import errno
import time
from statistics import mean, median
from typing import Dict, List

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
    parts: List[str] = []
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " <- ".join(parts)


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return float("nan")
    idx = int(round((pct / 100.0) * (len(values) - 1)))
    return sorted(values)[idx]


def _stats(latencies_ms: List[float]) -> Dict[str, float]:
    return {
        "count": float(len(latencies_ms)),
        "mean_ms": float(mean(latencies_ms)),
        "median_ms": float(median(latencies_ms)),
        "p95_ms": float(_percentile(latencies_ms, 95.0)),
        "min_ms": float(min(latencies_ms)),
        "max_ms": float(max(latencies_ms)),
    }


def _connect_client(host: str, port: int, use_tls: bool, cert_dir: Path) -> socket.socket:
    raw = socket.create_connection((host, port), timeout=5.0)
    raw.settimeout(5.0)
    if not use_tls:
        return raw

    ctx = create_tls_client_context(cert_dir=cert_dir, with_client_cert=True, trust_athena_ca=True)
    # Hostname check is disabled in helper context for loopback benchmarking.
    return ctx.wrap_socket(raw, server_hostname="ctrlbox")


def _benchmark_mode(
    mode_name: str,
    use_tls: bool,
    cert_dir: Path,
    payload_sizes: List[int],
    iterations: int,
    throughput_bytes: int,
) -> Dict[str, object]:
    server_ctx = create_tls_server_context(cert_dir, require_client_cert=True) if use_tls else None

    result: Dict[str, object] = {
        "mode": mode_name,
        "latency": {},
        "throughput": {},
    }

    with LocalEchoServer(tls_context=server_ctx) as server:
        with _connect_client("127.0.0.1", int(server.bound_port), use_tls=use_tls, cert_dir=cert_dir) as sock:
            for size in payload_sizes:
                payload = bytes([size % 251]) * size
                latencies_ms: List[float] = []

                # Warmup iterations to reduce first-sample noise.
                for _ in range(10):
                    sock.sendall(payload)
                    recv_exact(sock, size)

                for _ in range(iterations):
                    t0 = time.perf_counter_ns()
                    sock.sendall(payload)
                    recv_exact(sock, size)
                    t1 = time.perf_counter_ns()
                    latencies_ms.append((t1 - t0) / 1e6)

                result["latency"][str(size)] = _stats(latencies_ms)

            block_size = 4096
            payload = bytes([0xA5]) * block_size
            rounds = max(1, throughput_bytes // block_size)
            total_bytes = rounds * block_size

            t0 = time.perf_counter()
            for _ in range(rounds):
                sock.sendall(payload)
                recv_exact(sock, block_size)
            elapsed_s = max(1e-9, time.perf_counter() - t0)

            result["throughput"] = {
                "total_bytes": total_bytes,
                "elapsed_s": elapsed_s,
                "mb_per_s": (total_bytes / (1024.0 * 1024.0)) / elapsed_s,
            }

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cert-dir",
        type=Path,
        default=Path("etc") / "certs",
        help="Directory containing ca.crt/server.crt/server.key/instbox.crt/instbox.key",
    )
    parser.add_argument(
        "--sizes",
        default="20,256,1024,4096",
        help="Comma-separated payload sizes in bytes",
    )
    parser.add_argument("--iterations", type=int, default=200, help="Latency iterations per payload size")
    parser.add_argument(
        "--throughput-bytes",
        type=int,
        default=8 * 1024 * 1024,
        help="Total bytes for throughput test",
    )
    parser.add_argument("--skip-tls", action="store_true", help="Skip TLS benchmark and run TCP only")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("build") / "network_security_performance_report.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    payload_sizes = [int(token.strip()) for token in args.sizes.split(",") if token.strip()]
    if not payload_sizes:
        raise ValueError("--sizes must contain at least one payload size")

    report: Dict[str, object] = {
        "revision": build_revision_record(extra={"tool": "network_security_performance"}),
        "skipped": False,
        "config": {
            "payload_sizes": payload_sizes,
            "iterations": args.iterations,
            "throughput_bytes": args.throughput_bytes,
            "cert_dir": str(args.cert_dir),
        },
        "results": {},
    }

    try:
        tcp_result = _benchmark_mode(
            mode_name="tcp",
            use_tls=False,
            cert_dir=args.cert_dir,
            payload_sizes=payload_sizes,
            iterations=args.iterations,
            throughput_bytes=args.throughput_bytes,
        )
        report["results"]["tcp"] = tcp_result

        if not args.skip_tls:
            tls_result = _benchmark_mode(
                mode_name="mtls",
                use_tls=True,
                cert_dir=args.cert_dir,
                payload_sizes=payload_sizes,
                iterations=args.iterations,
                throughput_bytes=args.throughput_bytes,
            )
            report["results"]["mtls"] = tls_result

            # Add convenience deltas for quick interpretation.
            ratio = {}
            for size in payload_sizes:
                size_key = str(size)
                tcp_mean = tcp_result["latency"][size_key]["mean_ms"]
                tls_mean = tls_result["latency"][size_key]["mean_ms"]
                ratio[size_key] = tls_mean / tcp_mean if tcp_mean > 0 else float("inf")

            report["latency_overhead_ratio_mean_ms"] = ratio

            tcp_tp = tcp_result["throughput"]["mb_per_s"]
            tls_tp = tls_result["throughput"]["mb_per_s"]
            report["throughput_ratio_mtls_over_tcp"] = tls_tp / tcp_tp if tcp_tp > 0 else 0.0
    except Exception as exc:  # noqa: BLE001 - classify environment limitations
        if not _is_socket_permission_error(exc):
            raise
        report["skipped"] = True
        report["skip_reason"] = _describe_exception(exc)

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Network/security performance report written to {args.report}")
    if report["skipped"]:
        print(f"Benchmark skipped: {report['skip_reason']}")
        return 0

    print(f"TCP throughput: {report['results']['tcp']['throughput']['mb_per_s']:.3f} MB/s")
    if "mtls" in report["results"]:
        print(f"mTLS throughput: {report['results']['mtls']['throughput']['mb_per_s']:.3f} MB/s")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
