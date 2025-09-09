#!/usr/bin/env python3
"""
Tests for pke module (ReactorPowerCalculator)
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
import numpy as np

from arod_instrument.pke import ReactorPowerCalculator


class TestReactorPowerCalculator:
    """Test class for ReactorPowerCalculator"""

    def test_initialization_default_params(self):
        """Test ReactorPowerCalculator initialization with default parameters"""
        def dummy_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(dummy_reactivity)
        
        assert calc.get_reactivity == dummy_reactivity
        assert calc.dt == 0.1  # Default value
        assert calc.duration is None  # Default value
        assert calc.source_strength == 0.0
        assert calc.current_neutron_density == 1.0
        assert calc.MAX_REACTOR_POWER == 1e30
        assert calc.current_rho == 0.0
        assert isinstance(calc.results, list)
        assert len(calc.results) == 0
        assert isinstance(calc.stop_event, threading.Event)

    def test_initialization_custom_params(self):
        """Test ReactorPowerCalculator initialization with custom parameters"""
        def dummy_reactivity():
            return 0.0
        
        update_event = threading.Event()
        explosion_event = threading.Event()
        
        calc = ReactorPowerCalculator(
            dummy_reactivity, 
            dt=0.05, 
            duration=5.0, 
            update_event=update_event,
            explosion_event=explosion_event
        )
        
        assert calc.dt == 0.05
        assert calc.duration == 5.0
        assert calc.update_event == update_event
        assert calc.explosion_event == explosion_event

    def test_set_source(self):
        """Test set_source method"""
        def dummy_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(dummy_reactivity)
        
        # Initially zero
        assert calc.source_strength == 0.0
        
        # Set to non-zero value
        calc.set_source(1e6)
        assert calc.source_strength == 1e6
        
        # Set back to zero
        calc.set_source(0.0)
        assert calc.source_strength == 0.0

    def test_stop_method(self):
        """Test stop method sets the stop event"""
        def dummy_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(dummy_reactivity)
        
        # Initially not set
        assert not calc.stop_event.is_set()
        
        # Call stop
        calc.stop()
        
        # Should be set now
        assert calc.stop_event.is_set()

    @patch('arod_instrument.pke.time')
    def test_run_zero_reactivity_short_duration(self, mock_time):
        """Test run method with zero reactivity for short duration"""
        def zero_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(zero_reactivity, dt=0.1, duration=0.2)
        
        # Mock time to control timing - need more values for timing calculations
        call_count = 0
        def mock_time_func():
            nonlocal call_count
            # Return sequence: start_time, step1_start, step1_end, step2_start, step2_end
            times = [0.0, 0.05, 0.1, 0.15, 0.2, 0.25]
            if call_count < len(times):
                result = times[call_count]
                call_count += 1
                return result
            return times[-1]  # Return last time for any additional calls
            
        mock_time.time.side_effect = mock_time_func
        mock_time.sleep = Mock()  # Mock sleep to avoid actual delays
        
        # Mock the solver to return predictable results
        with patch.object(calc.solver, 'solve') as mock_solve:
            # Mock solver returns: (time_array, state_array)
            mock_solve.side_effect = [
                (np.array([0.1]), np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])),  # t=0.1
                (np.array([0.2]), np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])),  # t=0.2
            ]
            
            calc.run()
        
        # Should have completed 2 timesteps
        assert len(calc.results) == 2
        
        # Check results structure: (time, reactivity, neutron_density)
        assert len(calc.results[0]) == 3
        assert calc.results[0][1] == 0.0  # Zero reactivity
        assert calc.results[0][2] == 1.0  # Neutron density
        
        # Should have called solver twice
        assert mock_solve.call_count == 2

    @patch('arod_instrument.pke.time')
    def test_run_positive_reactivity(self, mock_time):
        """Test run method with positive constant reactivity"""
        reactivity_value = 0.001
        
        def positive_reactivity():
            return reactivity_value
        
        calc = ReactorPowerCalculator(positive_reactivity, dt=0.1, duration=0.2)
        
        # Simple time mock that returns increasing values
        mock_time.time.return_value = 0.1  # Keep time constant for simplicity
        mock_time.sleep = Mock()
        
        with patch.object(calc.solver, 'solve') as mock_solve:
            # Simulate increasing neutron density due to positive reactivity
            mock_solve.side_effect = [
                (np.array([0.1]), np.array([[1.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])),  # Increased
                (np.array([0.2]), np.array([[1.10, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])),  # Further increased
            ]
            
            calc.run()
        
        # Check that reactivity was properly passed to solver
        assert len(calc.results) == 2
        assert calc.results[0][1] == reactivity_value
        assert calc.results[0][2] == 1.05  # Increased neutron density
        assert calc.results[1][2] == 1.10  # Further increased

    def test_run_explosion_scenario_simple(self):
        """Test run method handles power explosion scenario (simplified)"""
        def high_reactivity():
            return 0.01  # High positive reactivity
        
        explosion_event = threading.Event()
        calc = ReactorPowerCalculator(
            high_reactivity, 
            dt=0.01, 
            duration=0.02,  # Very short duration
            explosion_event=explosion_event
        )
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.return_value = 0.01
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                # Simulate explosion on first step
                mock_solve.return_value = (
                    np.array([0.01]), 
                    np.array([[2e30, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])  # Exceeds MAX_REACTOR_POWER
                )
                
                # Capture print output
                with patch('builtins.print') as mock_print:
                    calc.run()
                
                # Should have printed explosion message
                explosion_calls = [call for call in mock_print.call_args_list 
                                 if 'exploded' in str(call)]
                assert len(explosion_calls) > 0
        
        # Should have set explosion event
        assert explosion_event.is_set()

    @patch('arod_instrument.pke.time')
    def test_run_with_update_event(self, mock_time):
        """Test run method signals update_event"""
        def zero_reactivity():
            return 0.0
        
        update_event = threading.Event()
        calc = ReactorPowerCalculator(
            zero_reactivity, 
            dt=0.1, 
            duration=0.1,
            update_event=update_event
        )
        
        mock_time.time.side_effect = [0.0, 0.1, 0.2]
        mock_time.sleep = Mock()
        
        with patch.object(calc.solver, 'solve') as mock_solve:
            mock_solve.return_value = (
                np.array([0.1]), 
                np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
            )
            
            # Reset event before run
            update_event.clear()
            
            calc.run()
        
        # Update event should have been set
        assert update_event.is_set()

    def test_run_stop_event_interruption_simple(self):
        """Test run method stops when stop_event is set"""
        def zero_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(zero_reactivity, dt=0.01, duration=10.0)  # Long duration
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.return_value = 0.01
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                mock_solve.return_value = (
                    np.array([0.01]), 
                    np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
                )
                
                # Set stop event immediately
                calc.stop_event.set()
                
                calc.run()
        
        # Should have stopped immediately without processing
        assert len(calc.results) == 0

    def test_run_duration_limit_simple(self):
        """Test run method respects duration limit"""
        def zero_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(zero_reactivity, dt=0.1, duration=0.05)  # Very short duration
        
        # Use a counter to track time progression
        time_counter = [0.0]  # Mutable counter
        
        def mock_time_func():
            result = time_counter[0]
            time_counter[0] += 0.1  # Increment by dt each call
            return result
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.side_effect = mock_time_func
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                mock_solve.return_value = (
                    np.array([0.1]), 
                    np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
                )
                
                calc.run()
        
        # Should have processed only a limited number of steps due to duration
        # The exact number depends on timing, but should be small
        assert len(calc.results) <= 2  # Should be limited by short duration

    def test_run_current_values_update(self):
        """Test that run method updates current neutron density and reactivity"""
        reactivity_value = 0.005
        
        def test_reactivity():
            return reactivity_value
        
        calc = ReactorPowerCalculator(test_reactivity, dt=0.01, duration=0.01)
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.side_effect = [0.0, 0.01, 0.02]
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                mock_solve.return_value = (
                    np.array([0.01]), 
                    np.array([[1.25, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
                )
                
                calc.run()
        
        # Check current values are updated
        assert calc.current_rho == reactivity_value
        assert calc.current_neutron_density == 1.25

    def test_run_solver_configuration_simple(self):
        """Test that run method properly configures the solver (simplified)"""
        reactivity_calls = []
        
        def tracking_reactivity():
            call_count = len(reactivity_calls)
            result = call_count * 0.001
            reactivity_calls.append(result)
            return result
        
        calc = ReactorPowerCalculator(tracking_reactivity, dt=0.01, duration=0.02)
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.return_value = 0.01
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                mock_solve.return_value = (
                    np.array([0.01]), 
                    np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
                )
                
                calc.run()
        
        # Should have called get_reactivity at least once
        assert len(reactivity_calls) >= 1
        assert mock_solve.call_count >= 1

    def test_source_strength_integration(self):
        """Test that source strength is properly integrated with solver"""
        def zero_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(zero_reactivity)
        
        # Initially zero
        assert calc.source_strength == 0.0
        assert calc.solver.source_func(0) == 0.0
        
        # Set source strength
        calc.set_source(1e5)
        assert calc.source_strength == 1e5
        assert calc.solver.source_func(0) == 1e5  # Should be updated through lambda
        
        # Change again
        calc.set_source(2e5)
        assert calc.source_strength == 2e5
        assert calc.solver.source_func(0) == 2e5

    def test_thread_inheritance(self):
        """Test that ReactorPowerCalculator properly inherits from Thread"""
        def dummy_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(dummy_reactivity)
        
        # Should be a Thread
        assert isinstance(calc, threading.Thread)
        
        # Should have Thread methods
        assert hasattr(calc, 'start')
        assert hasattr(calc, 'join')
        assert hasattr(calc, 'is_alive')

    def test_debug_mode_output(self):
        """Test debug mode produces output"""
        def zero_reactivity():
            return 0.0
        
        calc = ReactorPowerCalculator(zero_reactivity, dt=0.1, duration=0.1)
        calc.DEBUG = 3  # Enable debug output
        
        with patch('arod_instrument.pke.time') as mock_time:
            mock_time.time.side_effect = [0.0, 0.1, 0.2]
            mock_time.sleep = Mock()
            
            with patch.object(calc.solver, 'solve') as mock_solve:
                mock_solve.return_value = (
                    np.array([0.1]), 
                    np.array([[1.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6]])
                )
                
                with patch('builtins.print') as mock_print:
                    calc.run()
        
        # Should have debug print statements
        assert mock_print.call_count > 0