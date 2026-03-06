"""Real-time reactor power integration thread.

This module wraps :class:`arod_instrument.solver.PointKineticsEquationSolver`
in a pacing loop so the simulation can run continuously in near real time and
publish the latest power and reactivity values to other threads.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List, Optional, Tuple

import numpy as np

from arod_instrument.solver import PointKineticsEquationSolver


class ReactorPowerCalculator(threading.Thread):
    """Threaded real-time point-kinetics calculator.

    Parameters
    ----------
    get_reactivity:
        Callback returning the current reactivity insertion.
    dt:
        Integration time step in seconds.
    duration:
        Optional total simulated duration in seconds. ``None`` means run until
        :meth:`stop` is called.
    update_event:
        Optional event set after each successful integration step.
    explosion_event:
        Optional event set when computed neutron density exceeds
        :attr:`MAX_REACTOR_POWER` or becomes non-finite.

    Notes
    -----
    Results are appended to :attr:`results` as
    ``(elapsed_wall_time_s, rho, neutron_density)`` tuples.
    """

    def __init__(
        self,
        get_reactivity: Callable[[], float],
        dt: float = 0.1,
        duration: Optional[float] = None,
        update_event: Optional[threading.Event] = None,
        explosion_event: Optional[threading.Event] = None,
    ) -> None:
        super().__init__()
        if not np.isfinite(dt) or dt <= 0.0:
            raise ValueError("'dt' must be a positive finite number")
        if duration is not None and (not np.isfinite(duration) or duration < 0.0):
            raise ValueError("'duration' must be None or a non-negative finite number")

        self.get_reactivity: Callable[[], float] = get_reactivity
        self.dt: float = float(dt)
        self.duration: Optional[float] = float(duration) if duration is not None else None

        self.stop_event: threading.Event = threading.Event()
        self.explosion_event: Optional[threading.Event] = explosion_event
        self.update_event: Optional[threading.Event] = update_event

        self.results: List[Tuple[float, float, float]] = []
        self.source_strength: float = 0.0

        self.solver: PointKineticsEquationSolver = PointKineticsEquationSolver(
            lambda _t: 0.0,
            source_func=lambda _t: self.source_strength,
        )

        self.current_neutron_density: float = 1.0
        self.current_rho: float = 0.0
        self.MAX_REACTOR_POWER: float = 1e30
        self.DEBUG: int = 0

    def set_source(self, strength: float) -> None:
        """Set external source strength used by the kinetics solver.

        Parameters
        ----------
        strength:
            Source term passed into ``Q(t)`` in neutron-density equation.
        """
        self.source_strength = float(strength)

    def _steady_state_state(self) -> np.ndarray:
        """Return steady-state initial state vector ``[n, C1..Ck]``."""
        beta = self.solver.beta
        lambda_ = self.solver.lambda_
        Lambda = self.solver.Lambda
        n0 = 1.0
        c0 = beta / (lambda_ * Lambda) * n0
        return np.concatenate(([n0], c0))

    def run(self) -> None:
        """Run the real-time simulation loop until duration/stop condition."""
        beta_total = self.solver.beta_total
        state = self._steady_state_state()

        t_current: float = 0.0
        start_time = time.time()

        if self.DEBUG > 2:
            print(state)
            print("Time (s)\tReactivity\tNeutron Density (Power)")

        while not self.stop_event.is_set():
            if self.duration is not None and t_current >= self.duration:
                break

            rho = float(self.get_reactivity())
            self.solver.reactivity_func = lambda _t: rho

            try:
                sol_t, sol_y = self.solver.solve(
                    t_span=(t_current, t_current + self.dt),
                    t_eval=np.array([t_current + self.dt]),
                    y0_override=state,
                )
                del sol_t  # We only need the latest state from this single-step solve.
                state = np.asarray(sol_y).reshape(-1)
            except Exception:
                # Keep simulator running in a safe state if a single solve step fails.
                state = self._steady_state_state()

            current_power = float(state[0])
            if (not np.isfinite(current_power)) or current_power > self.MAX_REACTOR_POWER:
                print(" *** POWER OVER 1e30, your reactor exploded! Resetting reactor kinetics. *** ")
                if self.explosion_event:
                    self.explosion_event.set()
                state = self._steady_state_state()
                current_power = float(state[0])

            current_time = time.time() - start_time
            if self.DEBUG > 2:
                print(f"{current_time:.2f}\t{rho / beta_total:.6f}\t{current_power:.6f}")

            self.results.append((current_time, rho, current_power))
            self.current_rho = rho
            self.current_neutron_density = current_power

            if self.update_event:
                self.update_event.set()

            # Keep simulation paced to wall-clock time.
            t_current += self.dt
            elapsed = time.time() - start_time - t_current
            time.sleep(max(0.0, self.dt - elapsed))

    def stop(self) -> None:
        """Signal thread loop to stop at the next check."""
        self.stop_event.set()


# # Example of a real-time reactivity function (replace with actual data source)
# def get_reactivity():
#     # Simulated reactivity signal with time
#     return 0.001 * np.sin(2 * np.pi * 0.1 * (time.time() % 1000))
#
# # Usage:
# # calculator = ReactorPowerCalculator(get_reactivity, dt=0.1)
# # calculator.start()
# # ...
# # To stop safely from another thread or signal handler:
# # calculator.stop()
# # calculator.join()
