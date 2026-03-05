#!/usr/bin/env python3
"""Run a point-kinetics step-reactivity case from JSON input.

Usage:
    python -m examples.pke.run_step_case examples/pke/input_step_reactivity.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from arod_instrument.solver import PointKineticsEquationSolver, thermal_default_params


def _load_case(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m examples.pke.run_step_case <case.json>")
        return 2

    case = _load_case(Path(sys.argv[1]))

    beta_total = float(np.sum(thermal_default_params["beta"]))
    rho_step = float(case["reactivity_dollars"]) * beta_total
    step_time = float(case["step_time_s"])
    source_strength = float(case.get("source_strength", 0.0))

    def reactivity_func(t: float) -> float:
        return rho_step if t >= step_time else 0.0

    solver = PointKineticsEquationSolver(
        reactivity_func=reactivity_func,
        source_func=lambda _t: source_strength,
        params=thermal_default_params,
    )

    t_start = float(case["t_start_s"])
    t_end = float(case["t_end_s"])
    n_points = int(case["num_points"])
    t_eval = np.linspace(t_start, t_end, n_points)

    t, y = solver.solve((t_start, t_end), t_eval=t_eval)
    neutron = y[0]

    print(f"description: {case['description']}")
    print(f"final_time_s: {t[-1]:.6f}")
    print(f"initial_neutron_density: {neutron[0]:.6f}")
    print(f"final_neutron_density: {neutron[-1]:.6f}")
    print(f"peak_neutron_density: {np.max(neutron):.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
