"""
Examples for running PointKineticsEquationSolver, FuchsNordheimSolver, and
the new PKEFuchsNordheimSolver, and generating plots of the results.
"""
import numpy as np
import matplotlib.pyplot as plt
from arod_instrument.solver import PointKineticsEquationSolver, FuchsNordheimSolver, PKEFuchsNordheimSolver, \
    thermal_default_params


def run_pke_example():
    """
    Demonstrates the use of the PointKineticsEquationSolver with a step
    reactivity insertion.
    """
    print("--- Running PointKineticsEquationSolver Example ---")

    beta_total = thermal_default_params['beta'].sum()
    reactivity_dollars = 0.5

    # Define a reactivity function: a step insertion of 0.5$ at t=1s
    # The solver expects reactivity in absolute units.
    def reactivity_step(t: float) -> float:
        if t < 1.0:
            return 0.0
        else:
            return reactivity_dollars * beta_total

    # Time span for the simulation
    t_span = (0, 20)
    t_eval = np.linspace(t_span[0], t_span[1], 1000)
    # Initialize the solver
    pke_solver = PointKineticsEquationSolver(reactivity_func=reactivity_step, params=thermal_default_params)
    # Solve the equations
    pke_solver.solve(t_span, t_eval=t_eval)
    print("PKE solution complete. Generating plots...")
    # Plot the results
    pke_solver.plot_neutron_density(title=f"PKE: Neutron Density after ${reactivity_dollars} Step")
    pke_solver.plot_precursors(title=f"PKE: Precursors after ${reactivity_dollars} Step")
    print("PKE plots generated.")


def run_fuchs_nordheim_example():
    """
    Demonstrates the use of the FuchsNordheimSolver for a rapid
    super-prompt-critical reactivity insertion.
    """
    print("\n--- Running FuchsNordheimSolver Example ---")

    beta_total = thermal_default_params['beta'].sum()
    rho_dollars = 1.2  # 1.2$ insertion, which is super-prompt-critical

    # Physical parameters for the model
    fn_params = {'rho0': rho_dollars * beta_total,  # Initial reactivity insertion (absolute)
        'alpha_T': -2.5e-5,  # Temperature coefficient of reactivity [dk/K]
        'm_Cp': 2.0e7,  # Heat capacity of the core [J/K]
        'T0': 20.0,  # Initial temperature [°C]
    }

    print(f"Initial reactivity insertion: {fn_params['rho0']:.5f} (or ${rho_dollars})")
    # Time span for the simulation: 5 minutes (300 seconds)
    t_span = (0, 300)
    # Create a non-uniform time grid to capture the fast pulse and the long cooldown
    t_pulse = np.linspace(0, 1, 2000)  # High resolution for the first second
    t_cooldown = np.linspace(1, t_span[1], 1000)  # Lower resolution for the rest
    t_eval = np.unique(np.concatenate((t_pulse, t_cooldown)))

    # Initialize the solver
    fn_solver = FuchsNordheimSolver(params=thermal_default_params, **fn_params)
    # Solve the equations
    fn_solver.solve(t_span, t_eval=t_eval)
    # Plot the results
    fn_solver.plot_power_and_temperature(title=f"Fuchs-Nordheim Pulse for ${rho_dollars} Insertion")
    print("Fuchs-Nordheim plot generated.")


def run_pke_fuchs_nordheim_example():
    """
    Demonstrates the use of the PKEFuchsNordheimSolver for a
    reactivity insertion with delayed neutrons and temperature feedback.
    """
    print("\n--- Running PKEFuchsNordheimSolver Example ---")

    beta_total = thermal_default_params['beta'].sum()
    rho_dollars = 1.2  # 1.2$ insertion

    # Physical parameters
    pke_fn_params = {'rho0': rho_dollars * beta_total, 'alpha_T': -2.5e-5, 'm_Cp': 2.0e7, 'T0': 20.0}
    print(f"Initial reactivity insertion: {pke_fn_params['rho0']:.5f} (or ${rho_dollars})")

    # Time span for the simulation: 5 minutes (300 seconds)
    t_span = (0, 300)
    # Create a non-uniform time grid to capture the fast pulse and the long cooldown
    t_pulse = np.linspace(0, 1, 2000)  # High resolution for the first second
    t_cooldown = np.linspace(1, t_span[1], 1000)  # Lower resolution for the rest
    t_eval = np.unique(np.concatenate((t_pulse, t_cooldown)))

    # Initialize the solver
    pke_fn_solver = PKEFuchsNordheimSolver(params=thermal_default_params, **pke_fn_params)
    # Solve the equations
    pke_fn_solver.solve(t_span, t_eval=t_eval)
    print("PKE-Fuchs-Nordheim solution complete. Generating plot...")
    # Plot the results
    pke_fn_solver.plot_power_and_temperature(title=f"PKE with Feedback for ${rho_dollars} Insertion")
    print("PKE-Fuchs-Nordheim plot generated.")


if __name__ == "__main__":
    run_pke_example()
    run_fuchs_nordheim_example()
    run_pke_fuchs_nordheim_example()

    # Display all the plots from all examples
    print("\nDisplaying all plots...")
    plt.show()
