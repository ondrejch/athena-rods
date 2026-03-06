"""Numerical solvers for reactor point-kinetics models.

This module provides three ODE-based models used in ATHENA-rods:

- :class:`PointKineticsEquationSolver`: delayed-neutron point kinetics with
  optional external neutron source.
- :class:`FuchsNordheimSolver`: prompt-jump approximation with temperature
  feedback.
- :class:`PKEFuchsNordheimSolver`: delayed-neutron point kinetics coupled to a
  lumped thermal feedback equation.

All models are integrated using :func:`scipy.integrate.solve_ivp` with RK45.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp
from scipy.integrate._ivp.ivp import OdeResult


thermal_default_params: Dict[str, Any] = {
    "beta": np.array([0.000215, 0.00142, 0.00127, 0.00257, 0.00075, 0.00027], dtype=float),
    "lambda_": np.array([0.0126, 0.0337, 0.139, 0.325, 1.13, 2.50], dtype=float),
    "Lambda": 5e-4,
    "fission_energy": 3.2e-11,  # J per fission
    "nu": 2.43,  # neutrons per fission
}

fast_reactor_params: Dict[str, Any] = {
    "beta": np.array([0.00022, 0.00142, 0.00127, 0.00257, 0.00075, 0.00027], dtype=float),
    "lambda_": np.array([0.0126, 0.0337, 0.139, 0.325, 1.13, 2.50], dtype=float),
    "Lambda": 1e-7,
    "fission_energy": 3.2e-11,
    "nu": 2.43,
}


def _as_1d_float_array(values: Any, name: str) -> np.ndarray:
    """Return ``values`` as a finite 1D ``float64`` NumPy array.

    Parameters
    ----------
    values:
        Input sequence or array-like object.
    name:
        Parameter name used in error messages.

    Returns
    -------
    np.ndarray
        One-dimensional floating-point array.
    """
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError(f"'{name}' must be a 1D array")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"'{name}' contains non-finite values")
    return array


def _validate_t_span(t_span: Tuple[float, float]) -> None:
    """Validate integration time interval."""
    if len(t_span) != 2:
        raise ValueError("t_span must be a 2-tuple (t_start, t_end)")
    t_start, t_end = float(t_span[0]), float(t_span[1])
    if not np.isfinite(t_start) or not np.isfinite(t_end):
        raise ValueError("t_span values must be finite")
    if t_end <= t_start:
        raise ValueError("t_span must satisfy t_end > t_start")


def _validate_t_eval(t_span: Tuple[float, float], t_eval: Optional[np.ndarray]) -> None:
    """Validate user-provided evaluation grid."""
    if t_eval is None:
        return

    t_eval_arr = np.asarray(t_eval, dtype=float)
    if t_eval_arr.ndim != 1:
        raise ValueError("t_eval must be a 1D array")
    if t_eval_arr.size == 0:
        raise ValueError("t_eval must not be empty")
    if not np.all(np.isfinite(t_eval_arr)):
        raise ValueError("t_eval contains non-finite values")
    if np.any(np.diff(t_eval_arr) <= 0.0):
        raise ValueError("t_eval must be strictly increasing")

    t_start, t_end = t_span
    if t_eval_arr[0] < t_start or t_eval_arr[-1] > t_end:
        raise ValueError("t_eval values must stay within t_span")


class PointKineticsEquationSolver:
    """Solve delayed-neutron point kinetics equations.

    Parameters
    ----------
    reactivity_func:
        Function ``rho(t)`` returning external reactivity (absolute units).
    source_func:
        Optional external source ``Q(t)`` in neutron-density equation.
        If omitted, a zero-source model is used.
    params:
        Reactor parameter dictionary containing:
        ``beta`` (array), ``lambda_`` (array), and ``Lambda`` (float).

    Examples
    --------
    >>> import numpy as np
    >>> solver = PointKineticsEquationSolver(lambda t: 0.0)
    >>> t, y = solver.solve((0.0, 1.0), t_eval=np.linspace(0.0, 1.0, 11))
    >>> y.shape[0] == 1 + len(solver.beta)
    True
    """

    def __init__(
        self,
        reactivity_func: Callable[[float], float],
        source_func: Optional[Callable[[float], float]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        if params is None:
            params = thermal_default_params

        self.params: Dict[str, Any] = dict(params)
        self.beta: np.ndarray = _as_1d_float_array(self.params["beta"], "beta")
        self.lambda_: np.ndarray = _as_1d_float_array(self.params["lambda_"], "lambda_")
        self.Lambda: float = float(self.params["Lambda"])
        self._validate_parameters()

        # Precompute coefficients used at every RHS evaluation.
        self.beta_total: float = float(np.sum(self.beta))
        self.beta_div_Lambda: np.ndarray = self.beta / self.Lambda

        self.reactivity_func: Callable[[float], float] = reactivity_func
        self.source_func: Callable[[float], float] = source_func or (lambda _t: 0.0)
        self.solution: Optional[OdeResult] = None

    def _validate_parameters(self) -> None:
        """Validate reactor parameter consistency and physical bounds."""
        if len(self.beta) != len(self.lambda_) or len(self.beta) < 1:
            raise ValueError("Beta and lambda arrays must have equal length")
        if np.any(self.beta < 0.0):
            raise ValueError("'beta' values must be non-negative")
        if np.any(self.lambda_ <= 0.0):
            raise ValueError("'lambda_' values must be strictly positive")
        if not np.isfinite(self.Lambda) or self.Lambda <= 0.0:
            raise ValueError("'Lambda' must be a positive finite number")

    def _steady_state_initial_conditions(self) -> np.ndarray:
        """Build steady-state initial state for ``rho=0`` and no source."""
        n0 = 1.0
        c0 = self.beta / (self.lambda_ * self.Lambda) * n0
        return np.concatenate(([n0], c0))

    def _validate_state_vector(self, y0: np.ndarray) -> np.ndarray:
        """Validate and normalize initial state vector for PKE state."""
        y0_arr = np.asarray(y0, dtype=float)
        expected_len = 1 + len(self.beta)
        if y0_arr.ndim != 1 or y0_arr.size != expected_len:
            raise ValueError(
                f"Initial state must be 1D with length {expected_len} "
                f"(n + {len(self.beta)} precursor groups)"
            )
        if not np.all(np.isfinite(y0_arr)):
            raise ValueError("Initial state contains non-finite values")
        return y0_arr

    def solve(
        self,
        t_span: Tuple[float, float] = (0.0, 10.0),
        t_eval: Optional[np.ndarray] = None,
        y0_override: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Integrate the delayed-neutron point-kinetics ODE system.

        Parameters
        ----------
        t_span:
            Integration interval ``(t_start, t_end)`` in seconds.
        t_eval:
            Optional strictly increasing sampling times inside ``t_span``.
        y0_override:
            Optional state override ``[n, C1, ..., Ck]``.

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            ``(t, y)`` from SciPy, where ``y[0]`` is neutron density.
        """
        _validate_t_span(t_span)
        _validate_t_eval(t_span, t_eval)

        y0 = self._steady_state_initial_conditions() if y0_override is None else self._validate_state_vector(y0_override)
        beta_sum = self.beta_total
        beta_div_lambda = self.beta_div_Lambda
        lambda_ = self.lambda_
        Lambda = self.Lambda

        def equations(t: float, y: np.ndarray) -> np.ndarray:
            """Return time-derivative of neutron density and precursor groups."""
            n = float(y[0])
            c = y[1:]
            rho = float(self.reactivity_func(t))
            q = float(self.source_func(t))

            prompt = (rho - beta_sum) / Lambda
            delayed = float(np.dot(lambda_, c))

            dndt = n * prompt + delayed + q
            dcdt = beta_div_lambda * n - lambda_ * c
            return np.concatenate(([dndt], dcdt))

        result = solve_ivp(
            equations,
            t_span,
            y0,
            method="RK45",
            t_eval=t_eval,
            rtol=1e-6,
            atol=1e-8,
        )
        if not result.success:
            raise RuntimeError(f"PKE solver failed: {result.message}")

        self.solution = result
        return result.t, result.y

    def plot_neutron_density(
        self,
        figsize: Tuple[int, int] = (8, 4),
        logscale: bool = True,
        title: Optional[str] = None,
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot neutron-density history from the latest solution."""
        if self.solution is None:
            raise RuntimeError("Call solve() before plotting")

        fig, ax = plt.subplots(figsize=figsize)
        if logscale:
            ax.semilogy(self.solution.t, self.solution.y[0], **plot_kwargs)
        else:
            ax.plot(self.solution.t, self.solution.y[0], **plot_kwargs)

        plot_title = title if title is not None else "Point Kinetics Neutron Density"
        ax.set(xlabel="Time [s]", ylabel="Relative Neutron Density", title=plot_title)
        ax.grid(True, which="both" if logscale else "major", alpha=0.4)
        return fig, ax

    def plot_precursors(
        self,
        groups: Union[str, List[int]] = "all",
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot delayed-neutron precursor concentrations by group.

        Parameters
        ----------
        groups:
            ``"all"`` or a list of zero-based precursor indices.
        """
        if self.solution is None:
            raise RuntimeError("Call solve() before plotting")

        c_groups = self.solution.y[1:]
        if groups == "all":
            plot_groups = range(len(c_groups))
        else:
            plot_groups = list(groups)
            if not plot_groups:
                raise ValueError("'groups' must not be empty")
            max_idx = len(c_groups) - 1
            for idx in plot_groups:
                if idx < 0 or idx > max_idx:
                    raise IndexError(f"Precursor group index out of range: {idx}")

        fig, ax = plt.subplots(figsize=figsize)
        for idx in plot_groups:
            ax.plot(self.solution.t, c_groups[idx], label=f"Group {idx + 1}", **plot_kwargs)

        plot_title = title if title is not None else "Delayed Neutron Precursors"
        ax.set(xlabel="Time [s]", ylabel="Precursor Concentration", title=plot_title)
        ax.legend(loc="best")
        ax.grid(True, alpha=0.4)
        return fig, ax

    def plot_source_contribution(
        self,
        figsize: Tuple[int, int] = (8, 4),
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot sampled external source contribution ``Q(t)``."""
        if self.solution is None:
            raise RuntimeError("Call solve() before plotting")

        fig, ax = plt.subplots(figsize=figsize)
        source_values = [self.source_func(t) for t in self.solution.t]
        ax.plot(self.solution.t, source_values, "r--", linewidth=2, **plot_kwargs)
        ax.set(
            xlabel="Time (s)",
            ylabel="Source Strength [neutrons/s]",
            title="External Neutron Source Function",
        )
        ax.grid(True, alpha=0.4)
        return fig, ax

    def plot(self, figsize: Tuple[int, int] = (12, 6), logscale: bool = False, **_plot_kwargs: Any) -> Any:
        """Create a two-panel diagnostic plot (neutron + precursor groups)."""
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")

        t = self.solution.t
        n = self.solution.y[0]
        c = self.solution.y[1:]

        plt.figure(figsize=figsize)

        plt.subplot(1, 2, 1)
        if logscale:
            plt.semilogy(t, n, "b-", linewidth=2)
        else:
            plt.plot(t, n, "b-", linewidth=2)
        plt.xlabel("Time [s]", fontsize=12)
        plt.ylabel("Relative Neutron Density", fontsize=12)
        plt.title("Neutron Population", fontsize=14)
        plt.grid(True, which="both", linestyle="--", alpha=0.7)

        plt.subplot(1, 2, 2)
        for idx, c_i in enumerate(c):
            plt.plot(t, c_i, label=f"Group {idx + 1}")
        plt.xlabel("Time [s]", fontsize=12)
        plt.ylabel("Precursor Concentration", fontsize=12)
        plt.title("Precursors", fontsize=14)
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left")
        plt.grid(True, linestyle="--", alpha=0.7)
        return plt


class FuchsNordheimSolver:
    """Solve prompt-jump Fuchs-Nordheim burst equations.

    Parameters
    ----------
    alpha_T:
        Temperature feedback coefficient (reactivity per degree C).
    m_Cp:
        Lumped thermal capacitance in J / degree C.
    rho0:
        Initial inserted reactivity (absolute units).
    T0:
        Initial temperature in degree C.
    params:
        Optional reactor parameter mapping. ``Lambda`` and ``beta`` are used.
    """

    def __init__(
        self,
        alpha_T: float,
        m_Cp: float,
        rho0: float,
        T0: float = 20.0,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        if params is None:
            params = thermal_default_params

        self.params: Dict[str, Any] = dict(params)
        beta = _as_1d_float_array(self.params["beta"], "beta")
        self.Lambda: float = float(self.params["Lambda"])

        if not np.isfinite(self.Lambda) or self.Lambda <= 0.0:
            raise ValueError("'Lambda' must be a positive finite number")
        if not np.isfinite(m_Cp) or m_Cp <= 0.0:
            raise ValueError("'m_Cp' must be a positive finite number")

        self.beta_total: float = float(np.sum(beta))
        self.alpha_T: float = float(alpha_T)
        self.m_Cp: float = float(m_Cp)
        self.rho0: float = float(rho0)
        self.T0: float = float(T0)
        self.solution: Optional[OdeResult] = None

    def solve(
        self,
        t_span: Tuple[float, float],
        t_eval: Optional[np.ndarray] = None,
        y0_override: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Integrate the two-state Fuchs-Nordheim ODE system.

        State vector is ``[P, T]`` where ``P`` is relative power.
        """
        _validate_t_span(t_span)
        _validate_t_eval(t_span, t_eval)

        if y0_override is None:
            y0 = np.array([1.0e-10, self.T0], dtype=float)
        else:
            y0 = np.asarray(y0_override, dtype=float)
            if y0.ndim != 1 or y0.size != 2:
                raise ValueError("Initial state must be [P, T]")
            if not np.all(np.isfinite(y0)):
                raise ValueError("Initial state contains non-finite values")

        def equations(_t: float, y: np.ndarray) -> np.ndarray:
            p, temp = float(y[0]), float(y[1])

            # Negative alpha_T introduces stabilizing feedback as temperature rises.
            rho_t = self.rho0 + self.alpha_T * (temp - self.T0)
            dpdt = ((rho_t - self.beta_total) / self.Lambda) * p
            dtdt = p / self.m_Cp
            return np.array([dpdt, dtdt], dtype=float)

        result = solve_ivp(
            equations,
            t_span,
            y0,
            method="RK45",
            t_eval=t_eval,
            rtol=1e-8,
            atol=1e-10,
        )
        if not result.success:
            raise RuntimeError(f"Fuchs-Nordheim solver failed: {result.message}")

        self.solution = result
        return result.t, result.y

    def plot_power_and_temperature(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot power and temperature histories on twin y-axes."""
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")

        t = self.solution.t
        p = self.solution.y[0]
        temp = self.solution.y[1]

        fig, ax1 = plt.subplots(figsize=figsize)
        ax1.set_xlabel("Time [s]")
        ax1.set_ylabel("Relative Power", color="tab:blue")
        ax1.semilogy(t, p, color="tab:blue", label="Power", **plot_kwargs)
        ax1.tick_params(axis="y", labelcolor="tab:blue")
        ax1.grid(True, which="both", linestyle="--", alpha=0.7)

        ax2 = ax1.twinx()
        ax2.set_ylabel("Temperature [°C]", color="tab:red")
        ax2.plot(t, temp, color="tab:red", label="Temperature", **plot_kwargs)
        ax2.tick_params(axis="y", labelcolor="tab:red")

        plot_title = title if title is not None else "Fuchs-Nordheim Power and Temperature vs. Time"
        plt.title(plot_title)
        return fig, (ax1, ax2)


class PKEFuchsNordheimSolver(PointKineticsEquationSolver):
    """Coupled delayed-neutron kinetics with lumped thermal feedback.

    This model augments point-kinetics state with explicit power and
    temperature states:

    ``y = [n, P, C1, ..., Ck, T]``
    """

    def __init__(
        self,
        alpha_T: float,
        m_Cp: float,
        rho0: float,
        T0: float = 20.0,
        params: Optional[Dict[str, Any]] = None,
        source_func: Optional[Callable[[float], float]] = None,
    ) -> None:
        self.alpha_T = float(alpha_T)
        self.m_Cp = float(m_Cp)
        self.rho0 = float(rho0)
        self.T0 = float(T0)

        if not np.isfinite(self.m_Cp) or self.m_Cp <= 0.0:
            raise ValueError("'m_Cp' must be a positive finite number")

        # Reactivity closure used inside ODE RHS.
        def temp_feedback_reactivity(_t: float, temp: float) -> float:
            return self.rho0 + self.alpha_T * (temp - self.T0)

        self._temp_feedback_reactivity = temp_feedback_reactivity

        super().__init__(reactivity_func=lambda _t: self.rho0, source_func=source_func, params=params)

        self.fission_energy: float = float(self.params.get("fission_energy", 3.2e-11))
        self.nu: float = float(self.params.get("nu", 2.43))
        self.initial_power: float = float(self.params.get("initial_power", 1.0e-10))

        if not np.isfinite(self.fission_energy) or self.fission_energy <= 0.0:
            raise ValueError("'fission_energy' must be a positive finite number")
        if not np.isfinite(self.nu) or self.nu <= 0.0:
            raise ValueError("'nu' must be a positive finite number")
        if not np.isfinite(self.initial_power) or self.initial_power <= 0.0:
            raise ValueError("'initial_power' must be a positive finite number")

    def solve(
        self,
        t_span: Tuple[float, float],
        t_eval: Optional[np.ndarray] = None,
        y0_override: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Integrate coupled neutron, power, precursor, and temperature states."""
        _validate_t_span(t_span)
        _validate_t_eval(t_span, t_eval)

        beta_sum = self.beta_total
        beta_div_lambda = self.beta_div_Lambda
        lambda_ = self.lambda_
        Lambda = self.Lambda

        if y0_override is None:
            n0 = self.initial_power / (self.fission_energy / self.nu)
            p0 = self.initial_power
            c0 = self.beta / (lambda_ * Lambda) * n0
            y0 = np.concatenate(([n0], [p0], c0, [self.T0]))
        else:
            y0 = np.asarray(y0_override, dtype=float)
            expected_len = len(self.beta) + 3
            if y0.ndim != 1 or y0.size != expected_len:
                raise ValueError(
                    f"Initial state must be 1D with length {expected_len} "
                    f"([n, P, C1..Ck, T] for k={len(self.beta)})"
                )
            if not np.all(np.isfinite(y0)):
                raise ValueError("Initial state contains non-finite values")

        def equations(t: float, y: np.ndarray) -> np.ndarray:
            """Coupled point-kinetics + thermal feedback ODE system."""
            n = float(y[0])
            p = float(y[1])
            c = y[2:-1]
            temp = float(y[-1])

            rho = self._temp_feedback_reactivity(t, temp)
            q = float(self.source_func(t))

            prompt = (rho - beta_sum) / Lambda
            delayed = float(np.dot(lambda_, c))
            dndt = n * prompt + delayed + q

            # Keep power evolution tied to fission source term used by the model.
            dpdt = (self.fission_energy / self.nu) * (n * prompt + delayed)
            dcdt = beta_div_lambda * n - lambda_ * c
            dtdt = p / self.m_Cp
            return np.concatenate(([dndt], [dpdt], dcdt, [dtdt]))

        result = solve_ivp(
            equations,
            t_span,
            y0,
            method="RK45",
            t_eval=t_eval,
            rtol=1e-8,
            atol=1e-10,
        )
        if not result.success:
            raise RuntimeError(f"PKE-Fuchs-Nordheim solver failed: {result.message}")

        self.solution = result
        return result.t, result.y

    def get_temperature(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return ``(t, T)`` arrays from the latest coupled solution."""
        if self.solution is None:
            raise RuntimeError("Solver has not been run yet.")
        return self.solution.t, self.solution.y[-1]

    def plot_power_and_temperature(
        self,
        figsize: Tuple[int, int] = (10, 6),
        title: Optional[str] = None,
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot coupled power (W) and temperature (°C) on twin y-axes."""
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")

        t = self.solution.t
        p = self.solution.y[1]
        temp = self.solution.y[-1]

        fig, ax1 = plt.subplots(figsize=figsize)
        ax1.set_xlabel("Time [s]")
        ax1.set_ylabel("Power [W]", color="tab:blue")
        ax1.semilogy(t, p, color="tab:blue", label="Power", **plot_kwargs)
        ax1.tick_params(axis="y", labelcolor="tab:blue")
        ax1.grid(True, which="both", linestyle="--", alpha=0.7)

        ax2 = ax1.twinx()
        ax2.set_ylabel("Temperature [°C]", color="tab:red")
        ax2.plot(t, temp, color="tab:red", label="Temperature", **plot_kwargs)
        ax2.tick_params(axis="y", labelcolor="tab:red")

        plot_title = title if title is not None else "PKE with Temperature Feedback"
        plt.title(plot_title)
        return fig, (ax1, ax2)

    def plot_neutron_density(
        self,
        figsize: Tuple[int, int] = (8, 4),
        logscale: bool = True,
        title: Optional[str] = None,
        **plot_kwargs: Any,
    ) -> Tuple[Any, Any]:
        """Plot neutron-density state from the coupled solution."""
        if self.solution is None:
            raise RuntimeError("Call solve() before plotting")

        fig, ax = plt.subplots(figsize=figsize)
        if logscale:
            ax.semilogy(self.solution.t, self.solution.y[0], **plot_kwargs)
        else:
            ax.plot(self.solution.t, self.solution.y[0], **plot_kwargs)

        plot_title = title if title is not None else "Neutron Density"
        ax.set(xlabel="Time [s]", ylabel="Neutron Density", title=plot_title)
        ax.grid(True, which="both" if logscale else "major", alpha=0.4)
        return fig, ax
