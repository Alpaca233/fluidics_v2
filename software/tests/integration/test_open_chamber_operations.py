# tests/integration/test_open_chamber_operations.py
import pytest

from fluidics.open_chamber_operations import OpenChamberOperations


@pytest.fixture
def oc_ops(open_chamber_hardware):
    config, sp, sv, dp, tc = open_chamber_hardware
    return OpenChamberOperations(config, sp, sv, dp, tc)


class TestProcessSequence:
    def test_add_reagent(self, oc_ops):
        seq = {"type": "add_reagent", "fluidic_port": 3, "flow_rate": 1000, "volume": 1000}
        oc_ops.process_sequence(seq)

    def test_add_reagent_with_fill_tubing(self, oc_ops):
        seq = {"type": "add_reagent", "fluidic_port": 3, "flow_rate": 1000,
               "volume": 1000, "fill_tubing_with": 5}
        oc_ops.process_sequence(seq)

    def test_clear_and_add_reagent(self, oc_ops):
        seq = {"type": "clear_and_add_reagent", "fluidic_port": 3,
               "flow_rate": 1000, "volume": 1000}
        oc_ops.process_sequence(seq)

    def test_wash_constant_flow(self, oc_ops):
        seq = {"type": "wash_constant_flow", "fluidic_port": 6,
               "flow_rate": 1000, "volume": 1000}
        oc_ops.process_sequence(seq)

    def test_wash_constant_flow_with_fill_tubing(self, oc_ops):
        seq = {"type": "wash_constant_flow", "fluidic_port": 6,
               "flow_rate": 1000, "volume": 1000, "fill_tubing_with": 5}
        oc_ops.process_sequence(seq)

    def test_priming(self, oc_ops):
        seq = {"type": "priming", "fluidic_port": 10, "flow_rate": 1000, "volume": 1000}
        oc_ops.process_sequence(seq)

    def test_clean_up(self, oc_ops):
        seq = {"type": "clean_up", "fluidic_port": 10, "flow_rate": 1000, "volume": 1000}
        oc_ops.process_sequence(seq)

    def test_set_temperature(self, oc_ops):
        seq = {"type": "set_temperature", "temperature": 50}
        oc_ops.process_sequence(seq)

    def test_unknown_type_raises(self, oc_ops):
        seq = {"type": "nonexistent"}
        with pytest.raises(ValueError, match="Unknown sequence type"):
            oc_ops.process_sequence(seq)
