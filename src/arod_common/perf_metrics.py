"""Performance metrics for step-response style control tests."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

import numpy as np


@dataclass
class StepResponseMetrics:
    """Standard scalar metrics extracted from a step response."""

    initial_value: float
    final_value: float
    delta: float
    response_delay_s: Optional[float]
    rise_time_s: Optional[float]
    settling_time_s: Optional[float]
    overshoot_pct: float
    steady_state_error: float
    peak_value: float
    minimum_value: float

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics dataclass to a JSON-serializable dictionary."""
        return asdict(self)


def _crossing_time(times: np.ndarray, values: np.ndarray, threshold: float, start_index: int) -> Optional[float]:
    """Find first threshold crossing time after ``start_index``."""
    for i in range(max(start_index, 1), len(values)):
        if values[i - 1] < threshold <= values[i]:
            # Linear interpolation between sample points for smoother timing estimate.
            dv = values[i] - values[i - 1]
            if abs(dv) < 1e-12:
                return float(times[i])
            w = (threshold - values[i - 1]) / dv
            return float(times[i - 1] + w * (times[i] - times[i - 1]))
    return None


def compute_step_response_metrics(
    times: np.ndarray,
    signal: np.ndarray,
    step_time: float,
    tolerance_band: float = 0.02,
) -> StepResponseMetrics:
    """Compute control-performance metrics for a single step response.

    Parameters
    ----------
    times:
        Time vector in seconds (strictly increasing).
    signal:
        Response signal sampled at ``times``.
    step_time:
        Time when the step command was applied.
    tolerance_band:
        Settling tolerance as fraction of absolute step size.
    """
    t = np.asarray(times, dtype=float)
    y = np.asarray(signal, dtype=float)

    if t.ndim != 1 or y.ndim != 1 or len(t) != len(y):
        raise ValueError("times and signal must be 1D arrays of equal length")
    if len(t) < 4:
        raise ValueError("Need at least 4 samples to compute response metrics")
    if np.any(np.diff(t) <= 0.0):
        raise ValueError("times must be strictly increasing")

    step_index = int(np.searchsorted(t, step_time, side="left"))
    if step_index <= 1 or step_index >= len(t) - 2:
        raise ValueError("step_time must split pre-step and post-step windows")

    pre = y[:step_index]
    post = y[step_index:]

    initial = float(np.mean(pre[max(0, len(pre) // 2):]))
    final = float(np.mean(post[max(1, int(len(post) * 0.8)):]))
    delta = final - initial

    if abs(delta) < 1e-12:
        raise ValueError("Step response delta is too small for metric extraction")

    normalized = (y - initial) / delta
    # By construction, normalized response should move from ~0 to ~1 for both up and down steps.

    response_delay = _crossing_time(t, normalized, threshold=0.05, start_index=step_index)
    rise_10 = _crossing_time(t, normalized, threshold=0.10, start_index=step_index)
    rise_90 = _crossing_time(t, normalized, threshold=0.90, start_index=step_index)

    rise_time = None
    if rise_10 is not None and rise_90 is not None and rise_90 >= rise_10:
        rise_time = rise_90 - rise_10

    band = tolerance_band * abs(delta)
    settling_time = None
    for i in range(step_index, len(y)):
        if np.all(np.abs(y[i:] - final) <= band):
            settling_time = float(t[i] - step_time)
            break

    peak = float(np.max(y))
    minimum = float(np.min(y))

    if delta > 0.0:
        overshoot = max(0.0, (peak - final) / abs(delta) * 100.0)
    else:
        overshoot = max(0.0, (final - minimum) / abs(delta) * 100.0)

    steady_state_error = float(y[-1] - final)

    if response_delay is not None:
        response_delay = max(0.0, response_delay - step_time)

    return StepResponseMetrics(
        initial_value=initial,
        final_value=final,
        delta=float(delta),
        response_delay_s=response_delay,
        rise_time_s=rise_time,
        settling_time_s=settling_time,
        overshoot_pct=float(overshoot),
        steady_state_error=steady_state_error,
        peak_value=peak,
        minimum_value=minimum,
    )
