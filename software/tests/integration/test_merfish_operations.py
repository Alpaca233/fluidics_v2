# tests/integration/test_merfish_operations.py
import pytest

from fluidics.merfish_operations import MERFISHOperations


class TestProcessSequence:
    @pytest.fixture
    def ops(self, flow_cell_hardware):
        config, sp, sv = flow_cell_hardware
        return MERFISHOperations(config, sp, sv)

    def test_flow_reagent(self, ops):
        seq = {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000, "volume": 500}
        ops.process_sequence(seq)  # should not raise

    def test_flow_reagent_with_fill_tubing(self, ops):
        seq = {"type": "flow_reagent", "fluidic_port": 2, "flow_rate": 5000,
               "volume": 2000, "fill_tubing_with": 25}
        ops.process_sequence(seq)

    def test_priming(self, ops):
        seq = {"type": "priming", "fluidic_port": 10, "flow_rate": 5000, "volume": 2000}
        ops.process_sequence(seq)

    def test_clean_up(self, ops):
        seq = {"type": "clean_up", "fluidic_port": 10, "flow_rate": 10000, "volume": 2000}
        ops.process_sequence(seq)

    def test_unknown_type_raises(self, ops):
        seq = {"type": "nonexistent", "fluidic_port": 1, "flow_rate": 100, "volume": 100}
        with pytest.raises(ValueError, match="Unknown sequence type"):
            ops.process_sequence(seq)
