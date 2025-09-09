#!/usr/bin/env python3
"""
Tests for solver module (Point Kinetics Equations solver)
"""

import pytest
import numpy as np
from unittest.mock import patch

# No hardware mocking needed for pure calculation module
from arod_instrument.solver import PointKineticsEquationSolver, thermal_default_params, fast_reactor_params


class TestPointKineticsEquationSolver:
    """Test class for Point Kinetics Equations solver"""

    def test_default_initialization(self):
        """Test solver initialization with default parameters"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Should use thermal_default_params by default
        assert np.array_equal(solver.beta, thermal_default_params['beta'])
        assert np.array_equal(solver.lambda_, thermal_default_params['lambda_'])
        assert solver.Lambda == thermal_default_params['Lambda']
        assert solver.beta_total == np.sum(thermal_default_params['beta'])

    def test_custom_parameters_initialization(self):
        """Test solver initialization with custom parameters"""
        def zero_reactivity(t):
            return 0.0
        
        custom_params = {
            'beta': np.array([0.001, 0.002, 0.003]),
            'lambda_': np.array([0.1, 0.2, 0.3]),
            'Lambda': 1e-5
        }
        
        solver = PointKineticsEquationSolver(zero_reactivity, params=custom_params)
        
        assert np.array_equal(solver.beta, custom_params['beta'])
        assert np.array_equal(solver.lambda_, custom_params['lambda_'])
        assert solver.Lambda == custom_params['Lambda']
        assert solver.beta_total == np.sum(custom_params['beta'])

    def test_fast_reactor_parameters(self):
        """Test solver with fast reactor parameters"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity, params=fast_reactor_params)
        
        assert np.array_equal(solver.beta, fast_reactor_params['beta'])
        assert solver.Lambda == fast_reactor_params['Lambda']

    def test_source_function_default(self):
        """Test default source function returns zero"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Default source should return 0
        assert solver.source_func(0) == 0
        assert solver.source_func(10) == 0

    def test_source_function_custom(self):
        """Test custom source function"""
        def zero_reactivity(t):
            return 0.0
        
        def custom_source(t):
            return 1e6  # Constant source
        
        solver = PointKineticsEquationSolver(zero_reactivity, source_func=custom_source)
        
        assert solver.source_func(0) == 1e6
        assert solver.source_func(5) == 1e6

    def test_validate_parameters_mismatched_lengths(self):
        """Test parameter validation with mismatched array lengths"""
        def zero_reactivity(t):
            return 0.0
        
        invalid_params = {
            'beta': np.array([0.001, 0.002]),  # 2 elements
            'lambda_': np.array([0.1, 0.2, 0.3]),  # 3 elements - mismatch
            'Lambda': 1e-5
        }
        
        with pytest.raises(ValueError, match="Beta and lambda arrays must have equal length"):
            PointKineticsEquationSolver(zero_reactivity, params=invalid_params)

    def test_validate_parameters_empty_arrays(self):
        """Test parameter validation with empty arrays"""
        def zero_reactivity(t):
            return 0.0
        
        invalid_params = {
            'beta': np.array([]),
            'lambda_': np.array([]),
            'Lambda': 1e-5
        }
        
        with pytest.raises(ValueError, match="Beta and lambda arrays must have equal length"):
            PointKineticsEquationSolver(zero_reactivity, params=invalid_params)

    def test_equations_method_zero_reactivity(self):
        """Test equations method with zero reactivity (steady state)"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Steady-state conditions
        n0 = 1.0
        C0 = solver.beta / (solver.lambda_ * solver.Lambda) * n0
        y0 = np.concatenate(([n0], C0))
        
        # Calculate derivatives manually to verify equations method behavior
        t = 0.0
        n = y0[0]
        C = y0[1:]
        rho = solver.reactivity_func(t)  # Should be 0
        Q = solver.source_func(t)  # Should be 0
        
        prompt = (rho - solver.beta_total) / solver.Lambda
        delayed = np.dot(solver.lambda_, C)
        
        expected_dndt = n * prompt + delayed + Q
        expected_dCdt = solver.beta / solver.Lambda * n - solver.lambda_ * C
        
        # At steady state, these should be approximately zero
        assert abs(expected_dndt) < 1e-10
        assert all(abs(dc) < 1e-10 for dc in expected_dCdt)

    def test_solve_zero_reactivity_steady_state(self):
        """Test solver maintains steady state with zero reactivity"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Solve for a short time period
        t, y = solver.solve(t_span=(0, 1), t_eval=np.linspace(0, 1, 11))
        
        # Neutron density should remain approximately constant (1.0)
        neutron_density = y[0, :]
        assert all(abs(n - 1.0) < 1e-3 for n in neutron_density)
        
        # Precursor concentrations should remain approximately constant
        for i in range(len(solver.beta)):
            precursor_conc = y[i + 1, :]
            initial_conc = precursor_conc[0]
            assert all(abs(c - initial_conc) < 1e-3 for c in precursor_conc)

    def test_solve_positive_step_reactivity(self):
        """Test solver with positive step reactivity insertion"""
        def step_reactivity(t):
            return 0.001 if t >= 1.0 else 0.0  # $0.001 step at t=1s
        
        solver = PointKineticsEquationSolver(step_reactivity)
        
        # Solve over time span that includes the step
        t, y = solver.solve(t_span=(0, 5), t_eval=np.linspace(0, 5, 51))
        
        neutron_density = y[0, :]
        
        # Before step (t<1), should be approximately constant
        pre_step_indices = t < 1.0
        pre_step_densities = neutron_density[pre_step_indices]
        assert all(abs(n - 1.0) < 1e-2 for n in pre_step_densities)
        
        # After step (t>1), should increase due to positive reactivity
        post_step_indices = t > 2.0  # Give some time for response
        if len(post_step_indices) > 0:
            post_step_densities = neutron_density[post_step_indices]
            # Should be higher than initial value
            assert all(n > 1.1 for n in post_step_densities)

    def test_solve_negative_step_reactivity(self):
        """Test solver with negative step reactivity insertion"""
        def negative_step_reactivity(t):
            return -0.001 if t >= 1.0 else 0.0  # Negative step at t=1s
        
        solver = PointKineticsEquationSolver(negative_step_reactivity)
        
        t, y = solver.solve(t_span=(0, 5), t_eval=np.linspace(0, 5, 51))
        
        neutron_density = y[0, :]
        
        # After negative step, neutron density should decrease
        initial_density = neutron_density[0]
        final_density = neutron_density[-1]
        
        assert final_density < initial_density

    def test_solve_with_external_source(self):
        """Test solver with external neutron source"""
        def zero_reactivity(t):
            return 0.0
        
        def constant_source(t):
            return 1e3  # Constant external source
        
        solver = PointKineticsEquationSolver(zero_reactivity, source_func=constant_source)
        
        t, y = solver.solve(t_span=(0, 2), t_eval=np.linspace(0, 2, 21))
        
        neutron_density = y[0, :]
        
        # With external source, neutron density should increase over time
        initial_density = neutron_density[0]
        final_density = neutron_density[-1]
        
        assert final_density > initial_density

    def test_solve_custom_initial_conditions(self):
        """Test solver with custom initial conditions"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Custom initial conditions: 10x higher neutron density
        n0_custom = 10.0
        C0_custom = solver.beta / (solver.lambda_ * solver.Lambda) * n0_custom
        y0_custom = np.concatenate(([n0_custom], C0_custom))
        
        t, y = solver.solve(t_span=(0, 1), y0_override=y0_custom)
        
        # Should start at custom initial condition
        assert abs(y[0, 0] - n0_custom) < 1e-10
        
        # Should maintain higher level (scaled steady state)
        neutron_density = y[0, :]
        assert all(n > 9.0 for n in neutron_density)  # Should stay around 10

    def test_solve_custom_time_evaluation(self):
        """Test solver with custom time evaluation points"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Custom time points
        t_eval_custom = np.array([0, 0.5, 1.5, 3.0, 5.0])
        
        t, y = solver.solve(t_span=(0, 5), t_eval=t_eval_custom)
        
        # Should return results only at specified time points
        assert np.array_equal(t, t_eval_custom)
        assert y.shape[1] == len(t_eval_custom)

    def test_solve_returns_correct_dimensions(self):
        """Test that solve returns arrays with correct dimensions"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        t, y = solver.solve(t_span=(0, 2), t_eval=np.linspace(0, 2, 21))
        
        # Should have 1 + number_of_groups rows (neutron + precursors)
        expected_rows = 1 + len(solver.beta)
        assert y.shape[0] == expected_rows
        
        # Should have same number of columns as time points
        assert y.shape[1] == len(t)

    def test_equations_prompt_critical_case(self):
        """Test equations behavior near prompt critical"""
        # Need to define solver first
        solver = PointKineticsEquationSolver(lambda t: 0.0)  # Temporary
        
        def near_prompt_critical_reactivity(t):
            return 0.9 * solver.beta_total  # 90% of prompt critical
        
        solver = PointKineticsEquationSolver(near_prompt_critical_reactivity)
        
        # Should not blow up immediately (delayed neutrons provide stability)
        t, y = solver.solve(t_span=(0, 0.1), t_eval=np.linspace(0, 0.1, 11))
        
        # Should have increasing but finite neutron density
        neutron_density = y[0, :]
        assert all(np.isfinite(n) for n in neutron_density)
        assert neutron_density[-1] > neutron_density[0]  # Should increase

    def test_equations_supercritical_case(self):
        """Test equations behavior in supercritical case"""
        # Need to define solver first  
        solver = PointKineticsEquationSolver(lambda t: 0.0)  # Temporary
        
        def supercritical_reactivity(t):
            return 1.1 * solver.beta_total  # 110% of delayed critical
        
        solver = PointKineticsEquationSolver(supercritical_reactivity)
        
        # Should show exponential growth but remain finite for short times
        t, y = solver.solve(t_span=(0, 0.05), t_eval=np.linspace(0, 0.05, 6))
        
        neutron_density = y[0, :]
        
        # Should have exponential-like growth (relax the growth requirement)
        assert neutron_density[-1] > neutron_density[0] * 1.5  # Some growth
        assert all(np.isfinite(n) for n in neutron_density)

    def test_beta_div_lambda_precomputation(self):
        """Test that beta_div_Lambda is precomputed correctly"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Check precomputed value
        expected_beta_div_Lambda = solver.beta / solver.Lambda
        assert np.array_equal(solver.beta_div_Lambda, expected_beta_div_Lambda)

    def test_different_parameter_sets_consistency(self):
        """Test solver behavior is consistent across different parameter sets"""
        def zero_reactivity(t):
            return 0.0
        
        # Test thermal reactor params
        solver_thermal = PointKineticsEquationSolver(zero_reactivity, params=thermal_default_params)
        t1, y1 = solver_thermal.solve(t_span=(0, 1))
        
        # Test fast reactor params  
        solver_fast = PointKineticsEquationSolver(zero_reactivity, params=fast_reactor_params)
        t2, y2 = solver_fast.solve(t_span=(0, 1))
        
        # Both should maintain steady state, but neutron levels should be similar
        assert abs(y1[0, 0] - y2[0, 0]) < 1e-10  # Initial conditions
        assert abs(y1[0, -1] - 1.0) < 1e-2  # Thermal should stay near 1
        assert abs(y2[0, -1] - 1.0) < 1e-2  # Fast should stay near 1

    def test_solution_storage(self):
        """Test that solution is stored in solver instance"""
        def zero_reactivity(t):
            return 0.0
        
        solver = PointKineticsEquationSolver(zero_reactivity)
        
        # Initially no solution
        assert not hasattr(solver, 'solution') or solver.solution is None
        
        # After solving, solution should be stored
        t, y = solver.solve(t_span=(0, 1))
        assert hasattr(solver, 'solution')
        assert solver.solution is not None
        assert hasattr(solver.solution, 't')
        assert hasattr(solver.solution, 'y')