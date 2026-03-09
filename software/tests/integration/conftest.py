# tests/integration/conftest.py
import pytest

from fluidics.control.config import load_config
from fluidics.control.controller import FluidControllerSimulation
from fluidics.control.selector_valve import SelectorValveSystem
from fluidics.control.syringe_pump import SyringePumpSimulation


@pytest.fixture
def flow_cell_config(fixtures_dir):
    return load_config(str(fixtures_dir / "flow_cell_config.yaml"))


@pytest.fixture
def open_chamber_config(fixtures_dir):
    return load_config(str(fixtures_dir / "open_chamber_config.yaml"))


@pytest.fixture
def flow_cell_hardware(flow_cell_config):
    """Return (config, syringe_pump, selector_valves) for flow cell."""
    fc = FluidControllerSimulation(serial_number="test")
    sp = SyringePumpSimulation(
        sn=None,
        syringe_ul=flow_cell_config.syringe_pump.volume_ul,
        speed_code_limit=flow_cell_config.syringe_pump.speed_code_limit,
        waste_port=flow_cell_config.syringe_pump.waste_port,
    )
    sv = SelectorValveSystem(fc, flow_cell_config)
    return flow_cell_config, sp, sv
