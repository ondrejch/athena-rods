import numpy as np
import time
import threading
from solver import PointKineticsEquationSolver


class ReactorPowerCalculator(threading.Thread):
    def __init__(self, get_reactivity, dt=0.1, duration=None):
        super().__init__()
        self.get_reactivity = get_reactivity
        self.dt = dt
        self.duration = duration
        self.stop_event = threading.Event()
        self.results = []  # To store time, reactivity, power
        # self.solver = None
        # Initialize solver with dummy reactivity function; will update each step
        self.solver = PointKineticsEquationSolver(lambda t: 0.0)

    def run(self):
        beta = None
        lambda_ = None
        Lambda = None

        beta = self.solver.beta
        lambda_ = self.solver.lambda_
        Lambda = self.solver.Lambda

        # Initial steady-state conditions
        n0 = 1.0
        C0 = beta / (lambda_ * Lambda) * n0
        state = np.concatenate(([n0], C0))

        t_current = 0.0
        start_time = time.time()

        print("Time (s)\tReactivity\tNeutron Density (Power)")

        while not self.stop_event.is_set():
            if self.duration is not None and t_current >= self.duration:
                break

            # Get current reactivity
            rho = self.get_reactivity()

            # Define reactivity function constant over dt interval
            self.solver.reactivity_func = lambda t: rho

            # Solve equations for this time step
            sol = self.solver.solve(t_span=(t_current, t_current + self.dt), t_eval=[t_current + self.dt])
            state = sol[2][:, -1]
            neutron_density = state[0]

            current_time = time.time() - start_time
            print(f"{current_time:.2f}\t{rho:.6f}\t{neutron_density:.6f}")

            self.results.append((current_time, rho, neutron_density))

            t_current += self.dt

            # Sleep to maintain real-time pacing
            elapsed = time.time() - start_time - t_current
            time.sleep(max(0, self.dt - elapsed))

    def stop(self):
        self.stop_event.set()


# Example of a real-time reactivity function (replace with actual data source)
def get_reactivity():
    # Simulated reactivity signal with time
    return 0.001 * np.sin(2 * np.pi * 0.1 * (time.time() % 1000))

# Usage:
# calculator = ReactorPowerCalculator(get_reactivity, dt=0.1)
# calculator.start()
# ...
# To stop safely from another thread or signal handler:
# calculator.stop()
# calculator.join()
