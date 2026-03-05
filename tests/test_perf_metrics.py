#!/usr/bin/env python3
"""Tests for control-response metric extraction helpers."""

import numpy as np
import pytest

from arod_common.perf_metrics import compute_step_response_metrics


def test_compute_step_response_metrics_positive_step() -> None:
    t = np.linspace(0.0, 10.0, 1001)
    step_time = 1.0

    y = np.zeros_like(t)
    mask = t >= step_time
    # First-order response with a slight overshoot bump for realism.
    tau = 1.2
    y[mask] = 1.0 - np.exp(-(t[mask] - step_time) / tau)
    y[mask] += 0.02 * np.exp(-((t[mask] - 2.2) ** 2) / 0.15)

    metrics = compute_step_response_metrics(times=t, signal=y, step_time=step_time)

    assert metrics.delta > 0.0
    assert metrics.rise_time_s is not None and metrics.rise_time_s > 0.0
    assert metrics.response_delay_s is not None and metrics.response_delay_s >= 0.0
    assert metrics.overshoot_pct >= 0.0


def test_compute_step_response_metrics_negative_step() -> None:
    t = np.linspace(0.0, 10.0, 1001)
    step_time = 1.0

    y = np.ones_like(t)
    mask = t >= step_time
    tau = 1.0
    y[mask] = np.exp(-(t[mask] - step_time) / tau)

    metrics = compute_step_response_metrics(times=t, signal=y, step_time=step_time)
    assert metrics.delta < 0.0
    assert metrics.rise_time_s is not None and metrics.rise_time_s > 0.0


def test_compute_step_response_metrics_invalid_time_vector() -> None:
    t = np.array([0.0, 1.0, 1.0, 2.0])
    y = np.array([0.0, 0.1, 0.2, 0.3])
    with pytest.raises(ValueError, match="strictly increasing"):
        compute_step_response_metrics(times=t, signal=y, step_time=0.5)
