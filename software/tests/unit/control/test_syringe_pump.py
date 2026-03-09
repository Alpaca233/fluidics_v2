# tests/unit/control/test_syringe_pump.py
import pytest
from fluidics.control.syringe_pump import SyringePump, SyringePumpSimulation


class TestSpeedSecMapping:
    def test_mapping_length(self):
        assert len(SyringePump.SPEED_SEC_MAPPING) == 41  # speed codes 0-40

    def test_mapping_monotonically_increasing(self):
        mapping = SyringePump.SPEED_SEC_MAPPING
        for i in range(1, len(mapping)):
            assert mapping[i] >= mapping[i - 1], f"Not monotonic at index {i}"

    def test_simulation_has_same_mapping(self):
        assert SyringePump.SPEED_SEC_MAPPING == SyringePumpSimulation.SPEED_SEC_MAPPING


class TestFlowRateToSpeedCode:
    """Test the binary search algorithm using a real (non-simulated) pump's method.

    We can't instantiate SyringePump without hardware, so we test the algorithm
    by calling the method on a SyringePumpSimulation with volume/speed_code_limit
    patched, or by reimplementing the method call with known parameters.
    """

    @pytest.fixture
    def pump_sim(self):
        """Create a simulation pump that we can patch for testing."""
        p = SyringePumpSimulation(sn=None, syringe_ul=5000, speed_code_limit=10, waste_port=1)
        # Override flow_rate_to_speed_code with the real algorithm
        p.speed_code_limit = 10
        p.flow_rate_to_speed_code = SyringePump.flow_rate_to_speed_code.__get__(p)
        return p

    def test_exact_speed_code_match(self, pump_sim):
        """When target time exactly matches a mapping entry, return that code."""
        # speed code 0: 1.25 sec -> flow_rate = 5000*60/1250 = 240000 ul/min
        # speed code 12: 5.00 sec -> flow_rate = 5000*60/5000 = 60000 ul/min
        code = pump_sim.flow_rate_to_speed_code(60000)
        # target_time = 5000*60/60000 = 5.0, matches SPEED_SEC_MAPPING[12]
        assert code == 12

    def test_very_fast_rate_returns_speed_code_limit(self, pump_sim):
        """Flow rate faster than speed_code_limit → clamp to limit."""
        code = pump_sim.flow_rate_to_speed_code(999999)
        assert code == pump_sim.speed_code_limit

    def test_very_slow_rate_returns_max_code(self, pump_sim):
        """Flow rate slower than all mappings → return last code (40)."""
        code = pump_sim.flow_rate_to_speed_code(1)  # very slow
        assert code == 40

    def test_returns_closest_code(self, pump_sim):
        """Binary search finds the closest speed code."""
        code = pump_sim.flow_rate_to_speed_code(5000)
        # target_time = 5000*60/5000 = 60.0
        # SPEED_SEC_MAPPING[28] = 66.67, [27] = 60.00 → exact match
        assert code == 27

    def test_all_codes_reachable(self, pump_sim):
        """Every speed code from limit to 40 should be reachable by some flow rate.

        flow_rate_to_speed_code computes target_time = volume * 60 / rate and
        compares directly against SPEED_SEC_MAPPING, so we derive rates from
        that formula (without the *1000 used in get_flow_rate).
        """
        pump_sim.speed_code_limit = 0
        seen = set()
        mapping = SyringePump.SPEED_SEC_MAPPING
        for i in range(len(mapping)):
            # Rate that produces target_time == mapping[i]
            rate = pump_sim.volume * 60 / mapping[i]
            code = pump_sim.flow_rate_to_speed_code(rate)
            seen.add(code)
        # Every code should be reachable with its exact rate
        assert len(seen) == 41


class TestGetFlowRate:
    def test_known_values(self):
        """get_flow_rate returns volume * 60 / (mapping[code] * 1000)."""
        p = SyringePumpSimulation(sn=None, syringe_ul=5000, speed_code_limit=10, waste_port=1)
        # speed code 0 -> 1.25 sec -> 5000*60/(1.25*1000) = 240.0
        assert p.get_flow_rate(0) == 240.0
        # speed code 40 -> 600.0 sec -> 5000*60/(600*1000) = 0.5
        assert p.get_flow_rate(40) == 0.5

    def test_flow_rate_to_speed_code_round_trips(self):
        """flow_rate_to_speed_code round-trips when given rates in its own units.

        Note: get_flow_rate and flow_rate_to_speed_code use different unit
        conventions (get_flow_rate divides by 1000 extra), so we test
        flow_rate_to_speed_code's self-consistency separately.
        """
        p = SyringePumpSimulation(sn=None, syringe_ul=5000, speed_code_limit=0, waste_port=1)
        p.speed_code_limit = 0
        p.flow_rate_to_speed_code = SyringePump.flow_rate_to_speed_code.__get__(p)
        mapping = SyringePump.SPEED_SEC_MAPPING
        for code in range(41):
            # Rate that produces target_time == mapping[code]
            rate = p.volume * 60 / mapping[code]
            recovered_code = p.flow_rate_to_speed_code(rate)
            assert recovered_code == code, f"Round-trip failed for code {code}: rate={rate}, recovered={recovered_code}"
