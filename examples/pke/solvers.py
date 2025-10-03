"""
Examples for running PointKineticsEquationSolver and FuchsNordheimSolver
and generating plots of the results.
"""
import numpy as np
import matplotlib.pyplot as plt

from arod_instrument.solver import PointKineticsEquationSolver, FuchsNordheimSolver, thermal_default_params


def run_pke_example():
    """
    Demonstrates the use of the PointKineticsEquationSolver with a step
    reactivity insertion.
    """
    print("--- Running PointKineticsEquationSolver Example ---")

    # Define a reactivity function: a step insertion of 0.5$ at t=1s
    def reactivity_step(t: float) -> float:
        if t < 1.0:
            return 0.0
        else:
            # Reactivity is in dollars
            return 0.5 * thermal_default_params['beta'].sum()

    # Time span for the simulation
    t_span = (0, 20)
    t_eval = np.linspace(t_span[0], t_span[1], 1000)

    # Initialize the solver
    pke_solver = PointKineticsEquationSolver(reactivity_func=reactivity_step, params=thermal_default_params)

    # Solve the equations
    pke_solver.solve(t_span, t_eval=t_eval)

    print("PKE solution complete. Generating plots...")

    # Plot the results
    pke_solver.plot_neutron_density(title="PKE: Neutron Density after 0.5$ Step")
    pke_solver.plot_precursors(title="PKE: Precursor Concentrations after 0.5$ Step")

    print("PKE plots generated.")


def run_fuchs_nordheim_example():
    """
    Demonstrates the use of the FuchsNordheimSolver for a rapid
    super-prompt-critical reactivity insertion, simulated over a longer period.
    """
    print("\n--- Running FuchsNordheimSolver Example ---")

    # Parameters for a rapid excursion
    # Note: rho0 is in absolute reactivity units, not dollars ($)
    beta_total = thermal_default_params['beta'].sum()
    rho_dollars = 1.2  # 1.2$ insertion, which is super-prompt-critical

    # Physical parameters for the model
    # These are representative values and should be adjusted for a specific reactor
    fn_params = {'rho0': rho_dollars * beta_total,  # Initial reactivity insertion (absolute)
        'alpha_T': -5.0e-5,     # Temperature coefficient of reactivity [drho/K]
        'm_Cp': 1.5e7,          # Heat capacity of the core [J/°C]
        'T0': 20.0              # Initial temperature [°C]
    }

    print(f"Initial reactivity insertion: {fn_params['rho0']:.5f} (or {rho_dollars}$)")

    # Time span for the simulation: 5 minutes (300 seconds)
    t_span = (0, 300)

    # Create a non-uniform time grid to capture the fast pulse and the long cooldown
    # High resolution for the first 0.1 seconds, then lower resolution for the rest
    t_pulse = np.linspace(0, 0.1, 2000)
    t_cooldown = np.linspace(0.1, t_span[1], 1000)
    t_eval = np.unique(np.concatenate((t_pulse, t_cooldown)))

    # Initialize the solver
    fn_solver = FuchsNordheimSolver(params=thermal_default_params, **fn_params)

    # Solve the equations
    fn_solver.solve(t_span, t_eval=t_eval)

    print("Fuchs-Nordheim solution complete. Generating plot...")

    # Plot the results
    fn_solver.plot_power_and_temperature(title=f"Fuchs-Nordheim Pulse for {rho_dollars}$ Insertion (5 min simulation)")

    print("Fuchs-Nordheim plot generated.")


if __name__ == "__main__":
    # run_pke_example()
    run_fuchs_nordheim_example()

    # Display all the plots from both examples
    print("\nDisplaying all plots...")
    plt.show()
