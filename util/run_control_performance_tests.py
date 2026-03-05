#!/usr/bin/env python3
"""Run control-performance tests for ATHENA point-kinetics responses.

This script focuses on model/control-loop dynamics that are reproducible without
physical hardware. It computes canonical step-response metrics for both
positive and negative reactivity insertions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Dict, Tuple

import numpy as np

from arod_common.perf_metrics import compute_step_response_metrics
from arod_common.versioning import build_revision_record
from arod_instrument.solver import PointKineticsEquationSolver, thermal_default_params


def _simulate_step_case(
    reactivity_func: Callable[[float], float],
    t_span: Tuple[float, float],
    samples: int,
) -> Tuple[np.ndarray, np.ndarray]:
    solver = PointKineticsEquationSolver(reactivity_func=reactivity_func, params=thermal_default_params)
    t_eval = np.linspace(t_span[0], t_span[1], samples)
    t, y = solver.solve(t_span=t_span, t_eval=t_eval)
    return t, y[0]


def _evaluate_case(
    name: str,
    t: np.ndarray,
    neutron: np.ndarray,
    step_time: float,
    max_rise_time_s: float | None,
    max_settling_time_s: float | None,
    max_overshoot_pct: float | None,
) -> Dict[str, object]:
    metrics = compute_step_response_metrics(times=t, signal=neutron, step_time=step_time, tolerance_band=0.02)

    checks: list[tuple[str, bool]] = [
        ("nonzero_delta", abs(metrics.delta) > 1e-8),
        ("finite_overshoot", np.isfinite(metrics.overshoot_pct)),
        ("finite_steady_state_error", np.isfinite(metrics.steady_state_error)),
    ]

    if name == "positive_step":
        checks.append(("positive_direction", metrics.delta > 0.0))
    if name == "negative_step":
        checks.append(("negative_direction", metrics.delta < 0.0))

    if max_rise_time_s is not None:
        checks.append(("rise_time_threshold", metrics.rise_time_s is not None and metrics.rise_time_s <= max_rise_time_s))
    if max_settling_time_s is not None:
        checks.append(
            (
                "settling_time_threshold",
                metrics.settling_time_s is not None and metrics.settling_time_s <= max_settling_time_s,
            )
        )
    if max_overshoot_pct is not None:
        checks.append(("overshoot_threshold", metrics.overshoot_pct <= max_overshoot_pct))

    return {
        "name": name,
        "metrics": metrics.to_dict(),
        "checks": [{"name": check_name, "passed": bool(passed)} for check_name, passed in checks],
        "passed": all(passed for _check_name, passed in checks),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step-time", type=float, default=1.0, help="Step insertion time in seconds")
    parser.add_argument("--duration", type=float, default=20.0, help="Simulation duration in seconds")
    parser.add_argument("--samples", type=int, default=1000, help="Number of time samples")
    parser.add_argument("--rho-step", type=float, default=0.001, help="Absolute reactivity step magnitude")
    parser.add_argument("--max-rise-time-s", type=float, default=None, help="Optional rise-time threshold")
    parser.add_argument("--max-settling-time-s", type=float, default=None, help="Optional settling-time threshold")
    parser.add_argument("--max-overshoot-pct", type=float, default=None, help="Optional overshoot threshold")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("build") / "control_performance_report.json",
        help="JSON report output path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    t_span = (0.0, float(args.duration))
    step_time = float(args.step_time)
    rho_step = float(args.rho_step)

    if step_time <= t_span[0] or step_time >= t_span[1]:
        raise ValueError("--step-time must lie strictly inside the simulation interval")

    pos_reactivity = lambda t: rho_step if t >= step_time else 0.0
    neg_reactivity = lambda t: -rho_step if t >= step_time else 0.0

    t_up, n_up = _simulate_step_case(pos_reactivity, t_span=t_span, samples=int(args.samples))
    t_dn, n_dn = _simulate_step_case(neg_reactivity, t_span=t_span, samples=int(args.samples))

    case_results = [
        _evaluate_case(
            "positive_step",
            t_up,
            n_up,
            step_time,
            args.max_rise_time_s,
            args.max_settling_time_s,
            args.max_overshoot_pct,
        ),
        _evaluate_case(
            "negative_step",
            t_dn,
            n_dn,
            step_time,
            args.max_rise_time_s,
            args.max_settling_time_s,
            args.max_overshoot_pct,
        ),
    ]

    passed = all(case["passed"] for case in case_results)
    report = {
        "passed": passed,
        "config": {
            "step_time_s": step_time,
            "duration_s": args.duration,
            "samples": args.samples,
            "rho_step": rho_step,
            "max_rise_time_s": args.max_rise_time_s,
            "max_settling_time_s": args.max_settling_time_s,
            "max_overshoot_pct": args.max_overshoot_pct,
        },
        "revision": build_revision_record(extra={"tool": "control_performance"}),
        "cases": case_results,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"Control performance report written to {args.report}")
    for case in case_results:
        metrics = case["metrics"]
        print(
            f"{case['name']}: passed={case['passed']} "
            f"rise_time={metrics['rise_time_s']} settling={metrics['settling_time_s']} "
            f"overshoot={metrics['overshoot_pct']:.3f}%"
        )

    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
