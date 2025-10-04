""" Point Kinetics Equations solver in Python
** Copied from: https://github.com/ondrejch/VR1-openmc **
Ondrej Chvala <ochvala@utexas.edu>
MIT license
For a similar PKE implementations in MATLAB/Octave, see: https://github.com/ondrejch/PointKineticsOctave """

from typing import Callable, Dict, Any, Optional, Tuple, Union, List
import numpy as np
from scipy.integrate import solve_ivp
import matplotlib.pyplot as plt

thermal_default_params: Dict[str, Any] = {
    'beta': np.array([0.000215, 0.00142, 0.00127, 0.00257, 0.00075, 0.00027]),
    'lambda_': np.array([0.0126, 0.0337, 0.139, 0.325, 1.13, 2.50]),
    'Lambda': 5e-4
}

fast_reactor_params: Dict[str, Any] = {
    'beta': np.array([0.00022, 0.00142, 0.00127, 0.00257, 0.00075, 0.00027]),
    'lambda_': np.array([0.0126, 0.0337, 0.139, 0.325, 1.13, 2.50]),
    'Lambda': 1e-7
}


class PointKineticsEquationSolver:
    """Nuclear reactor point kinetics analyzer with modular plotting
    Parameters:
        - reactivity_func (callable): ρ(t) in dollars, a function describing the reactor's external reactivity over time.
        - source_func (callable, optional): Describes the external neutron source. Defaults to a function returning zero (no source).
        - params (dict, optional): Reactor parameters including 'beta', 'lambda_', and 'Lambda'. Defaults to U-235 thermal parameters.
    Processing Logic:
        - Validates that the length of 'beta' and 'lambda_' arrays are equal and not empty.
        - Initializes the neutron density and delayed neutron precursor concentrations at steady-state.
        - Uses Runge-Kutta method (RK45) for solving differential equations.
        - Offers plotting options for analyzing neuron density, precursor concentrations, and source contribution with optional logging in visual representations."""
    def __init__(self, reactivity_func: Callable[[float], float],
                 source_func: Optional[Callable[[float], float]] = None,
                 params: Optional[Dict[str, Any]] = None) -> None:
        """ Nuclear reactor point kinetics analyzer with modular plotting
        Args:
            reactivity_func (callable): ρ(t) in dollars
            params (dict): Reactor parameters (default: U-235 thermal) """
        if params is None:
            params = thermal_default_params
        self.params: Dict[str, Any] = params
        self.beta: np.ndarray = params['beta']
        self.lambda_: np.ndarray = params['lambda_']
        self.Lambda: float = params['Lambda']
        # Precompute constants for speed
        self.beta_total: float = np.sum(self.beta)
        self.beta_div_Lambda: np.ndarray = self.beta / self.Lambda
        self._validate_parameters()
        self.reactivity_func: Callable[[float], float] = reactivity_func
        if source_func is None:
            source_func = (lambda t: 0.0)  # Default: no source
        self.source_func: Callable[[float], float] = source_func
        self.solution: Optional[Any] = None

    def _validate_parameters(self) -> None:
        if len(self.params['beta']) != len(self.params['lambda_']) or len(self.params['beta']) < 1:
            raise ValueError("Beta and lambda arrays must have equal length")

    def solve(self, t_span: Tuple[float, float] = (0, 10),
              t_eval: Optional[np.ndarray] = None,
              y0_override: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Solve the point kinetics equations"""
        beta = self.params['beta']
        lambda_ = self.params['lambda_']
        Lambda = self.params['Lambda']
        beta_sum: float = self.beta_total
        beta_div_Lambda = self.beta_div_Lambda

        if y0_override is not None:
            y0 = y0_override
        else:        # Initial conditions (steady-state)
            n0 = 1.0
            C0 = beta / (lambda_ * Lambda) * n0
            y0 = np.concatenate(([n0], C0))

        def equations(t: float, y: np.ndarray) -> np.ndarray:
            """Calculate the rate of change in neutron population and precursor concentrations over time.
            Parameters:
                - t (float): Time variable.
                - y (list): Contains neutron density and concentrations of delayed neutron precursors.
            Returns:
                - list: A list comprising the rate of change of neutron density followed by the rates of change of each precursor concentration."""
            n: float = float(y[0])
            C: np.ndarray = np.array(y[1:])  # vectorize precursor concentrations
            rho: float = self.reactivity_func(t)       # External reactivity
            Q: float = self.source_func(t)             # External neutron source
            prompt: float = (rho - beta_sum) / Lambda
            delayed: float = np.dot(lambda_, C)

            dndt: float = n * prompt + delayed + Q
            # dCdt = [beta[i] / Lambda * n - lambda_[i] * C[i] for i in range(len(C))]
            dCdt: np.ndarray = beta_div_Lambda * n - lambda_ * np.array(C)  # Numpy vectorization
            return np.concatenate(([dndt], dCdt))

        self.solution = solve_ivp(equations, t_span, y0, method='RK45', t_eval=t_eval, rtol=1e-6, atol=1e-8)
        # print("**** SOLUTION: ", self.solution)
        return self.solution.t, self.solution.y

    def plot_neutron_density(self, figsize: Tuple[int, int] = (8, 4),
                             logscale: bool = True, title: Optional[str] = None,
                             **plot_kwargs: Any) -> Tuple[Any, Any]:
        """ Plot neutron density temporal evolution
        Args:
            logscale (bool): Use logarithmic y-axis
            title (str, optional): Title for the plot.
            **plot_kwargs: Matplotlib styling options """
        if not self.solution:
            raise RuntimeError("Call solve() before plotting")
        fig, ax = plt.subplots(figsize=figsize)
        if logscale:
            ax.semilogy(self.solution.t, self.solution.y[0], **plot_kwargs)
        else:
            ax.plot(self.solution.t, self.solution.y[0], **plot_kwargs)

        plot_title = title if title is not None else 'Point Kinetics Neutron Density'
        ax.set(xlabel='Time [s]', ylabel='Relative Neutron Density', title=plot_title)
        ax.grid(True, which='both' if logscale else 'major', alpha=0.4)
        return fig, ax

    def plot_precursors(self, groups: Union[str, List[int]] = 'all',
                        figsize: Tuple[int, int] = (10, 6), title: Optional[str] = None,
                        **plot_kwargs: Any) -> Tuple[Any, Any]:
        """ Plot precursor group concentrations
        Args:
            groups: List of group indices (0-based) or 'all'
            title (str, optional): Title for the plot.
            """
        if not self.solution:
            raise RuntimeError("Call solve() before plotting")

        fig, ax = plt.subplots(figsize=figsize)
        C = self.solution.y[1:]
        plot_groups = range(len(C)) if groups == 'all' else groups
        for i in plot_groups:
            ax.plot(self.solution.t, C[i], label=f'Group {i + 1}', **plot_kwargs)

        plot_title = title if title is not None else 'Delayed Neutron Precursors'
        ax.set(xlabel='Time [s]', ylabel='Precursor Concentration', title=plot_title)
        ax.legend(loc='best')
        ax.grid(True, alpha=0.4)
        return fig, ax

    def plot_source_contribution(self, figsize: Tuple[int, int] = (8, 4), **plot_kwargs: Any) -> Tuple[Any, Any]:
        """Plot the external source function over time"""
        if not self.solution:
            raise RuntimeError("Call solve() before plotting")

        fig, ax = plt.subplots(figsize=figsize)
        source_values = [self.source_func(t) for t in self.solution.t]

        ax.plot(self.solution.t, source_values, 'r--', linewidth=2, **plot_kwargs)
        ax.set(
            xlabel='Time (s)',
            ylabel='Source Strength [neutrons/s]',
            title='External Neutron Source Function'
        )
        ax.grid(True, alpha=0.4)
        # plt.show()
        return fig, ax

    def plot(self, figsize=(12, 6), logscale=False, **plot_kwargs):
        """ Generate diagnostic plots for neutron density and precursor concentrations """
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")
        t = self.solution.t
        n = self.solution.y[0]
        C = self.solution.y[1:]

        plt.figure(figsize=figsize)
        # Neutron density plot (log scale)
        plt.subplot(1, 2, 1)
        if logscale:
            plt.semilogy(t, n, 'b-', linewidth=2)
        else:
            plt.plot(t, n, 'b-', linewidth=2)
        plt.xlabel('Time [s]', fontsize=12)
        plt.ylabel('Relative Neutron Density', fontsize=12)
        plt.title('Neutron Population', fontsize=14)
        plt.grid(True, which='both', linestyle='--', alpha=0.7)

        # Precursor concentrations plot
        plt.subplot(1, 2, 2)
        for i, Ci in enumerate(C):
            plt.plot(t, Ci, label=f'Group {i + 1}')
        plt.xlabel('Time [s]', fontsize=12)
        plt.ylabel('Precursor Concentration', fontsize=12)
        plt.title('Precursors', fontsize=14)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.7)

        # plt.tight_layout()
        # plt.show()
        return plt


class FuchsNordheimSolver:
    """ Fuchs-Nordheim point kinetics model for rapid reactivity excursions.
    This model is an approximation for super-prompt-critical accidents where
    the effects of delayed neutrons and heat transfer are neglected during the
    initial power burst. Reactivity is modeled with a negative temperature feedback.
    Parameters:
        - alpha_T (float): Temperature coefficient of reactivity [dk/K/°C].
        - m_Cp (float): Product of core mass and specific heat capacity [J/°C].
        - rho0 (float): Initial reactivity insertion [absolute, not in $].
        - T0 (float): Initial temperature [°C].
        - params (dict, optional): Reactor parameters including 'beta' and 'Lambda'.
                                   Defaults to U-235 thermal parameters.
    """
    def __init__(self, alpha_T: float, m_Cp: float, rho0: float, T0: float = 20.0,
                 params: Optional[Dict[str, Any]] = None) -> None:
        if params is None:
            params = thermal_default_params
        self.params: Dict[str, Any] = params
        self.Lambda: float = params['Lambda']
        self.beta_total: float = np.sum(params['beta'])
        self.alpha_T: float = alpha_T
        self.m_Cp: float = m_Cp
        self.rho0: float = rho0
        self.T0: float = T0
        self.solution: Optional[Any] = None

    def solve(self, t_span: Tuple[float, float],
              t_eval: Optional[np.ndarray] = None,
              y0_override: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """ Solve the Fuchs-Nordheim equations.
        The state vector y is [P, T], where P is power and T is temperature.
        """
        if y0_override is not None:
            y0 = y0_override
        else:
            # Initial conditions: low initial power, initial temperature T0
            P0 = 1.0e-10
            y0 = np.array([P0, self.T0])

        def equations(t: float, y: np.ndarray) -> np.ndarray:
            """ System of ODEs for the Fuchs-Nordheim model.
            y[0] = P (Power)
            y[1] = T (Temperature)
            """
            P, T = y
            # Reactivity with temperature feedback
            rho_t = self.rho0 + self.alpha_T * (T - self.T0)
            # Prompt-only point kinetics equation
            dPdt = ((rho_t - self.beta_total) / self.Lambda) * P
            # Temperature increase from power
            dTdt = P / self.m_Cp
            return np.array([dPdt, dTdt])

        self.solution = solve_ivp(equations, t_span, y0, method='RK45', t_eval=t_eval, rtol=1e-8, atol=1e-10)
        return self.solution.t, self.solution.y

    def plot_power_and_temperature(self, figsize: Tuple[int, int] = (10, 6),
                                   title: Optional[str] = None, **plot_kwargs: Any) -> Tuple[Any, Any]:
        """ Plot the power and temperature over time. """
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")
        t = self.solution.t
        P = self.solution.y[0]
        T = self.solution.y[1]

        fig, ax1 = plt.subplots(figsize=figsize)

        color = 'tab:blue'
        ax1.set_xlabel('Time [s]')
        ax1.set_ylabel('Relative Power', color=color)
        ax1.semilogy(t, P, color=color, label='Power', **plot_kwargs)
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, which='both', linestyle='--', alpha=0.7)

        ax2 = ax1.twinx()
        color = 'tab:red'
        ax2.set_ylabel(f'Temperature [°C]', color=color)
        ax2.plot(t, T, color=color, label='Temperature', **plot_kwargs)
        ax2.tick_params(axis='y', labelcolor=color)

        # fig.tight_layout()
        plot_title = title if title is not None else 'Fuchs-Nordheim Power and Temperature vs. Time'
        plt.title(plot_title)
        return fig, (ax1, ax2)


class PKEFuchsNordheimSolver(PointKineticsEquationSolver):
    """
    Solves the point kinetics equations with temperature feedback.
    This combines the delayed neutron effects from PKE with the temperature
    feedback model from Fuchs-Nordheim.
    Parameters:
        - alpha_T (float): Temperature coefficient of reactivity [dk/K/°C].
        - m_Cp (float): Product of core mass and specific heat capacity [J/°C].
        - rho0 (float): Initial reactivity insertion [absolute, not in $].
        - T0 (float): Initial temperature [°C].
        - params (dict, optional): Reactor parameters. Defaults to thermal params.
    """
    def __init__(self, alpha_T: float, m_Cp: float, rho0: float, T0: float = 20.0,
                 params: Optional[Dict[str, Any]] = None,
                 source_func: Optional[Callable[[float], float]] = None) -> None:
        self.alpha_T = alpha_T
        self.m_Cp = m_Cp
        self.rho0 = rho0
        self.T0 = T0

        # The reactivity function is now internal and depends on temperature
        def temp_feedback_reactivity(t: float, T: float) -> float:
            return self.rho0 + self.alpha_T * (T - self.T0)
        self._temp_feedback_reactivity = temp_feedback_reactivity

        # Initialize the parent class, but we will override the ODE system
        super().__init__(reactivity_func=lambda t: self.rho0, source_func=source_func, params=params)

    def solve(self, t_span: Tuple[float, float],
              t_eval: Optional[np.ndarray] = None,
              y0_override: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """Solve the coupled PKE and temperature equations."""
        beta_sum: float = self.beta_total
        beta_div_Lambda = self.beta_div_Lambda
        lambda_ = self.lambda_
        Lambda = self.Lambda

        if y0_override is not None:
            y0 = y0_override
        else:
            # Initial conditions (steady-state for n and C, T0 for temp)
            n0 = 1.0e-10  # Start from very low power
            C0 = self.beta / (lambda_ * Lambda) * n0
            # State vector is [n, C_1, ..., C_N, T]
            y0 = np.concatenate(([n0], C0, [self.T0]))

        def equations(t: float, y: np.ndarray) -> np.ndarray:
            """Coupled ODEs for PKE with temperature feedback."""
            n = float(y[0])
            C = np.array(y[1:-1])  # Precursor concentrations
            T = float(y[-1])       # Temperature

            # Reactivity now depends on temperature
            rho = self._temp_feedback_reactivity(t, T)
            Q = self.source_func(t)

            # PKE equations
            prompt = (rho - beta_sum) / Lambda
            delayed = np.dot(lambda_, C)
            dndt = n * prompt + delayed + Q
            dCdt = beta_div_Lambda * n - lambda_ * C

            # Temperature equation
            dTdt = n / self.m_Cp

            return np.concatenate(([dndt], dCdt, [dTdt]))

        self.solution = solve_ivp(equations, t_span, y0, method='RK45', t_eval=t_eval, rtol=1e-8, atol=1e-10)
        return self.solution.t, self.solution.y

    def get_temperature(self) -> Tuple[np.ndarray, np.ndarray]:
        """Returns the time and core temperature from the solution."""
        if self.solution is None:
            raise RuntimeError("Solver has not been run yet.")
        return self.solution.t, self.solution.y[-1]

    def plot_power_and_temperature(self, figsize: Tuple[int, int] = (10, 6),
                                   title: Optional[str] = None, **plot_kwargs: Any) -> Tuple[Any, Any]:
        """ Plot the power (neutron density) and temperature over time. """
        if self.solution is None:
            raise RuntimeError("No solution available. Call solve() first.")
        t = self.solution.t
        P = self.solution.y[0]
        T = self.solution.y[-1]

        fig, ax1 = plt.subplots(figsize=figsize)

        color = 'tab:blue'
        ax1.set_xlabel('Time [s]')
        ax1.set_ylabel('Relative Power', color=color)
        ax1.semilogy(t, P, color=color, label='Power', **plot_kwargs)
        ax1.tick_params(axis='y', labelcolor=color)
        ax1.grid(True, which='both', linestyle='--', alpha=0.7)

        ax2 = ax1.twinx()
        color = 'tab:red'
        ax2.set_ylabel(f'Temperature [°C]', color=color)
        ax2.plot(t, T, color=color, label='Temperature', **plot_kwargs)
        ax2.tick_params(axis='y', labelcolor=color)

        plot_title = title if title is not None else 'PKE with Temperature Feedback'
        plt.title(plot_title)
        return fig, (ax1, ax2)
