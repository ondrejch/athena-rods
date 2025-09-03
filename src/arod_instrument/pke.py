import numpy as np
import time
import threading
from solver import PointKineticsEquationSolver


class ReactorPowerCalculator(threading.Thread):
    """Initializes an instance of a class to manage reactor kinetics simulation.
    Parameters:
        - get_reactivity (callable): A function that returns the reactivity at a given time.
        - dt (float, optional): The time step for the simulation. Default is 0.1.
        - duration (float, optional): The total time for which the simulation runs. Default is None.
    Processing Logic:
        - A threading.Event object is used to manage when the simulation should stop.
        - Simulation calculates neutron density over the specified time, dependent on reactor reactivity.
        - Results are stored as time, reactivity, and neutron density.
        - Maintains real-time pacing by sleeping for the precise required duration."""
    def __init__(self, get_reactivity, dt=0.1, duration=None, update_event=None):
        """Initializes an instance of a class to manage reactor kinetics simulation.
        Parameters:
            - get_reactivity (callable): A function that returns the reactivity at a given time.
            - dt (float, optional): The time step for the simulation. Default is 0.1.
            - duration (float, optional): The total time for which the simulation runs. Default is None.
        Returns:
            - None: This is an initializer and does not return a value."""
        super().__init__()
        self.get_reactivity = get_reactivity
        self.dt = dt
        self.duration = duration
        self.stop_event = threading.Event()
        self.results = []  # To store time, reactivity, power
        # self.solver = None
        # Initialize solver with dummy reactivity function; will update each step
        self.solver = PointKineticsEquationSolver(lambda t: 0.0)
        self.current_neutron_density = 1.0
        self.current_rho = 0.0
        self.update_event = update_event  # New event for signaling updates
        self.DEBUG = 3

    def run(self):
        """Execute a time-dependent simulation of neutron density in nuclear reactor kinetics.
        Parameters:
            None
        Returns:
            None: The function does not return a value but prints real-time simulation results and appends them to the results list.
        This function runs a simulation to solve equations for neutron density over specified time intervals.
        It fetches initial steady-state conditions using solver parameters, computes neutron density, and prints
        the output in real-time pacing, simulating how neutron density changes over time within a nuclear reactor."""

        beta = self.solver.beta
        lambda_ = self.solver.lambda_
        Lambda = self.solver.Lambda

        # Initial steady-state conditions
        n0 = 1.0
        C0 = beta / (lambda_ * Lambda) * n0
        state = np.concatenate(([n0], C0))

        t_current = 0.0
        start_time = time.time()

        if self.DEBUG > 2:
            print("Time (s)\tReactivity\tNeutron Density (Power)")

        while not self.stop_event.is_set():
            if self.duration is not None and t_current >= self.duration:
                break

            # Get current reactivity
            rho = self.get_reactivity()

            # Define reactivity function constant over dt interval
            self.solver.reactivity_func = lambda t: rho

            # Solve equations for this time step
            sol = self.solver.solve(t_span=(t_current, t_current + self.dt), t_eval=[t_current + self.dt],
                                    y0_override=state)
            state = sol[2][:, -1]
            neutron_density = state[0]

            current_time = time.time() - start_time
            if self.DEBUG > 2:
                print(f"{current_time:.2f}\t{rho:.6f}\t{neutron_density:.6f}")

            self.results.append((current_time, rho, neutron_density))
            self.current_rho = rho
            self.current_neutron_density = neutron_density

            # Signal stream_sender that new data is ready
            if self.update_event:
                self.update_event.set()

            # Sleep to maintain real-time pacing
            t_current += self.dt
            elapsed = time.time() - start_time - t_current
            time.sleep(max(0, self.dt - elapsed))

    def stop(self):
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
