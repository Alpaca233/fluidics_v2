# Unit Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a CI-ready pytest test suite covering config, sequences, syringe pump, selector valve, controller utilities, and operations (with mocks).

**Architecture:** pytest with fixtures derived from existing sample configs. Unit tests (pure logic) and integration tests (simulation classes + mocks) in separate directories. Existing hardware tests moved to `tests/hardware/`.

**Tech Stack:** pytest, pydantic, pyyaml, pandas (for CSV tests), numpy (for controller utils)

---

### Task 1: Test infrastructure setup

**Files:**
- Create: `software/pyproject.toml`
- Move: `software/tests/startup.py` -> `software/tests/hardware/startup.py`
- Move: `software/tests/demo.py` -> `software/tests/hardware/demo.py`
- Create: `software/tests/__init__.py`
- Create: `software/tests/unit/__init__.py`
- Create: `software/tests/unit/control/__init__.py`
- Create: `software/tests/integration/__init__.py`
- Create: `software/tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[tool.pytest.ini_options]
testpaths = ["tests/unit", "tests/integration"]
```

**Step 2: Move existing hardware tests**

```bash
mkdir -p tests/hardware
git mv tests/startup.py tests/hardware/startup.py
git mv tests/demo.py tests/hardware/demo.py
```

**Step 3: Create directory structure and __init__.py files**

```bash
mkdir -p tests/unit/control tests/integration tests/fixtures
touch tests/__init__.py tests/unit/__init__.py tests/unit/control/__init__.py tests/integration/__init__.py
```

**Step 4: Create shared conftest.py with fixture paths**

```python
# tests/conftest.py
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixtures_dir():
    return FIXTURES_DIR
```

**Step 5: Verify pytest discovers no tests yet**

Run: `cd software && python -m pytest --collect-only`
Expected: "no tests ran" (0 items collected)

**Step 6: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: set up pytest infrastructure, move hardware tests"
```

---

### Task 2: Test fixtures

**Files:**
- Create: `software/tests/fixtures/flow_cell_config.yaml`
- Create: `software/tests/fixtures/open_chamber_config.yaml`
- Create: `software/tests/fixtures/legacy_flow_cell_config.json`
- Create: `software/tests/fixtures/legacy_open_chamber_config.json`
- Create: `software/tests/fixtures/valid_sequences.yaml`
- Create: `software/tests/fixtures/legacy_sequences.csv`

**Step 1: Copy sample configs as test fixtures**

Copy `sample_config/flow_cell_config.yaml` and `sample_config/open_chamber_config.yaml` into `tests/fixtures/`.

**Step 2: Create legacy JSON fixtures**

Build legacy JSON config dicts that, when converted via `convert_legacy_config()`, produce the equivalent of the YAML fixtures. These should use the old field names:

For Flow Cell (legacy JSON):
```json
{
    "application": "MERFISH",
    "microcontroller": {"serial_number": "15579610"},
    "syringe_pump": {
        "serial_number": "A9TLZRF2",
        "volume_ul": 5000,
        "ports_allowed": [1, 2, 3],
        "waste_port": 3,
        "extract_port": 2,
        "dispense_port": null,
        "speed_code_limit": 10
    },
    "selector_valves": {
        "valve_ids_allowed": [0, 1, 2],
        "number_of_ports": {"0": 10, "1": 10, "2": 10},
        "tubing_fluid_amount_to_valve_ul": {"0": 800, "1": 1000, "2": 1140},
        "reagent_name_mapping": {
            "port_1": "reagent x", "port_2": "y", "port_3": "z",
            "port_4": "a", "port_5": "b", "port_6": "c",
            "port_7": "t", "port_8": "x", "port_9": "y",
            "port_10": "z", "port_11": "aa", "port_12": "bb",
            "port_13": "cc", "port_14": "dd", "port_15": "ee",
            "port_16": "ff", "port_17": "gg", "port_18": "hh",
            "port_19": "ii", "port_20": "j", "port_21": "k",
            "port_22": "l", "port_23": "m", "port_24": "n",
            "port_25": "buffer 1", "port_26": "buffer 2",
            "port_27": "buffer 3", "port_28": "buffer 4"
        },
        "tubing_fluid_amount_to_port_ul": {
            "port_1": 700, "port_2": 700, "port_3": 700, "port_4": 700,
            "port_5": 700, "port_6": 700, "port_7": 700, "port_8": 700,
            "port_9": 700, "port_10": 600, "port_11": 600, "port_12": 600,
            "port_13": 600, "port_14": 600, "port_15": 600, "port_16": 600,
            "port_17": 600, "port_18": 600, "port_19": 450, "port_20": 450,
            "port_21": 450, "port_22": 450, "port_23": 450, "port_24": 450,
            "port_25": 700, "port_26": 700, "port_27": 900, "port_28": 900
        }
    }
}
```

Key conversion math for Flow Cell:
- `common_tubing_fluid_amount_ul = old_valve_amounts[0] = 800`
- `new_valve_amounts[k] = old[k] - 800` → `{0: 0, 1: 200, 2: 340}`

For Open Chamber (legacy JSON):
```json
{
    "application": "Open Chamber",
    "microcontroller": {"serial_number": "13995710"},
    "syringe_pump": {
        "serial_number": "CRCOb13BN11",
        "volume_ul": 2500,
        "ports_allowed": [1, 2, 3],
        "waste_port": 1,
        "extract_port": 2,
        "dispense_port": 3,
        "speed_code_limit": 10
    },
    "selector_valves": {
        "valve_ids_allowed": [0],
        "number_of_ports": {"0": 10},
        "tubing_fluid_amount_to_valve_ul": {"0": 0},
        "reagent_name_mapping": {
            "port_1": "reagent x", "port_5": "buffer a", "port_6": "buffer b"
        },
        "tubing_fluid_amount_to_port_ul": {
            "port_1": 300, "port_2": 300, "port_3": 300, "port_4": 300,
            "port_5": 300, "port_6": 300, "port_7": 300, "port_8": 300,
            "port_9": 300, "port_10": 300
        }
    },
    "tubing_fluid_amount_sv_to_sp_ul": 300,
    "tubing_fluid_amount_sp_to_oc_ul": 900,
    "chamber_volume_ul": 1300,
    "temperature_controller": {
        "use_temperature_controller": false,
        "serial_number": "FAKE_TC_SN"
    }
}
```

**Step 3: Create valid sequences YAML fixture**

Copy `sample_sequences/merfish-experiment.yaml` to `tests/fixtures/valid_sequences.yaml`.

**Step 4: Create legacy CSV fixture**

```csv
sequence_name,fluidic_port,flow_rate,volume,fill_tubing_with,incubation_time,repeat,include
Flow Reagent,2,5000,2000,25,3.0,1,1
Priming,10,5000,2000,0,0,1,1
Clean Up,10,10000,2000,0,0,3,1
Set Temperature 50,0,0,0,0,0,1,0
```

**Step 5: Commit**

```bash
git add tests/fixtures/
git commit -m "test: add test fixtures for configs and sequences"
```

---

### Task 3: Unit tests for config.py

**Files:**
- Create: `software/tests/unit/control/test_config.py`
- Test: `software/fluidics/control/config.py`

**Step 1: Write tests**

```python
# tests/unit/control/test_config.py
import pytest
import yaml
from pydantic import ValidationError

from fluidics.control.config import (
    FluidicsConfig,
    SelectorValvesConfig,
    load_config,
    convert_legacy_config,
)


class TestFluidicsConfigLoading:
    def test_load_flow_cell_config(self, fixtures_dir):
        config = load_config(str(fixtures_dir / "flow_cell_config.yaml"))
        assert config.application == "Flow Cell"
        assert config.syringe_pump.volume_ul == 5000
        assert config.config_version == "2.0"

    def test_load_open_chamber_config(self, fixtures_dir):
        config = load_config(str(fixtures_dir / "open_chamber_config.yaml"))
        assert config.application == "Open Chamber"
        assert config.samples.chamber_volume_ul == 1300
        assert config.sample_selection_inlet.common_tubing_fluid_amount_ul == 900

    def test_flow_cell_has_no_open_chamber_fields(self, fixtures_dir):
        config = load_config(str(fixtures_dir / "flow_cell_config.yaml"))
        assert config.sample_selection_inlet is None
        assert config.samples is None
        assert config.temperature_controller is None

    def test_invalid_application_rejected(self):
        with pytest.raises(ValidationError):
            FluidicsConfig(
                config_version="2.0",
                microcontroller={"serial_number": "X"},
                syringe_pump={
                    "serial_number": "X", "volume_ul": 1000,
                    "ports_allowed": [1], "waste_port": 1,
                    "extract_port": 1, "speed_code_limit": 10,
                },
                reagent_selection={
                    "selector_valves": {
                        "valve_ids": [0], "number_of_ports": {0: 10},
                        "tubing_fluid_amount_to_valve_ul": {0: 0},
                        "tubing_fluid_amount_ul": {"port_1": 100},
                    },
                    "common_tubing_fluid_amount_ul": 100,
                },
                application="Invalid",
            )

    def test_syringe_volume_must_be_positive(self):
        with pytest.raises(ValidationError, match="volume_ul"):
            FluidicsConfig(
                config_version="2.0",
                microcontroller={"serial_number": "X"},
                syringe_pump={
                    "serial_number": "X", "volume_ul": 0,
                    "ports_allowed": [1], "waste_port": 1,
                    "extract_port": 1, "speed_code_limit": 10,
                },
                reagent_selection={
                    "selector_valves": {
                        "valve_ids": [0], "number_of_ports": {0: 10},
                        "tubing_fluid_amount_to_valve_ul": {0: 0},
                        "tubing_fluid_amount_ul": {"port_1": 100},
                    },
                    "common_tubing_fluid_amount_ul": 100,
                },
                application="Flow Cell",
            )

    def test_speed_code_limit_range(self):
        """speed_code_limit must be 0-40."""
        with pytest.raises(ValidationError, match="speed_code_limit"):
            FluidicsConfig(
                config_version="2.0",
                microcontroller={"serial_number": "X"},
                syringe_pump={
                    "serial_number": "X", "volume_ul": 1000,
                    "ports_allowed": [1], "waste_port": 1,
                    "extract_port": 1, "speed_code_limit": 41,
                },
                reagent_selection={
                    "selector_valves": {
                        "valve_ids": [0], "number_of_ports": {0: 10},
                        "tubing_fluid_amount_to_valve_ul": {0: 0},
                        "tubing_fluid_amount_ul": {"port_1": 100},
                    },
                    "common_tubing_fluid_amount_ul": 100,
                },
                application="Flow Cell",
            )


class TestSelectorValvesValidator:
    def test_mismatched_valve_ids_rejected(self):
        """number_of_ports keys must match valve_ids."""
        with pytest.raises(ValidationError, match="don't match valve_ids"):
            SelectorValvesConfig(
                valve_ids=[0, 1],
                number_of_ports={0: 10},  # missing valve 1
                tubing_fluid_amount_to_valve_ul={0: 0, 1: 100},
                tubing_fluid_amount_ul={"port_1": 100},
            )

    def test_extra_keys_in_number_of_ports_rejected(self):
        with pytest.raises(ValidationError, match="don't match valve_ids"):
            SelectorValvesConfig(
                valve_ids=[0],
                number_of_ports={0: 10, 1: 10},  # extra valve 1
                tubing_fluid_amount_to_valve_ul={0: 0},
                tubing_fluid_amount_ul={"port_1": 100},
            )

    def test_valid_multi_valve_config(self):
        sv = SelectorValvesConfig(
            valve_ids=[0, 1],
            number_of_ports={0: 10, 1: 10},
            tubing_fluid_amount_to_valve_ul={0: 0, 1: 200},
            tubing_fluid_amount_ul={"port_1": 100},
        )
        assert sv.valve_ids == [0, 1]


class TestConvertLegacyConfig:
    def test_flow_cell_conversion(self, fixtures_dir):
        """Legacy MERFISH JSON converts to valid Flow Cell YAML config."""
        import json
        with open(fixtures_dir / "legacy_flow_cell_config.json") as f:
            old = json.load(f)

        new = convert_legacy_config(old)
        config = FluidicsConfig(**new)

        assert config.application == "Flow Cell"
        assert config.config_version == "2.0"
        assert config.reagent_selection.common_tubing_fluid_amount_ul == 800
        # Verify tubing decomposition: common(800) + per_valve == original total
        sv = config.reagent_selection.selector_valves
        assert sv.tubing_fluid_amount_to_valve_ul[0] == 0    # 800 - 800
        assert sv.tubing_fluid_amount_to_valve_ul[1] == 200   # 1000 - 800
        assert sv.tubing_fluid_amount_to_valve_ul[2] == 340   # 1140 - 800

    def test_open_chamber_conversion(self, fixtures_dir):
        """Legacy Open Chamber JSON converts to valid config."""
        import json
        with open(fixtures_dir / "legacy_open_chamber_config.json") as f:
            old = json.load(f)

        new = convert_legacy_config(old)
        config = FluidicsConfig(**new)

        assert config.application == "Open Chamber"
        assert config.sample_selection_inlet.common_tubing_fluid_amount_ul == 900
        assert config.samples.chamber_volume_ul == 1300
        # temperature_controller with use_temperature_controller=False should NOT appear
        assert config.temperature_controller is None

    def test_merfish_becomes_flow_cell(self, fixtures_dir):
        import json
        with open(fixtures_dir / "legacy_flow_cell_config.json") as f:
            old = json.load(f)
        new = convert_legacy_config(old)
        assert new['application'] == 'Flow Cell'

    def test_empty_reagent_names_filtered(self):
        old = {
            "application": "MERFISH",
            "microcontroller": {"serial_number": "X"},
            "syringe_pump": {
                "serial_number": "X", "volume_ul": 1000,
                "ports_allowed": [1], "waste_port": 1,
                "extract_port": 1, "speed_code_limit": 10,
            },
            "selector_valves": {
                "valve_ids_allowed": [0],
                "number_of_ports": {"0": 10},
                "tubing_fluid_amount_to_valve_ul": {"0": 100},
                "reagent_name_mapping": {"port_1": "buffer", "port_2": "", "port_3": None},
                "tubing_fluid_amount_to_port_ul": {"port_1": 100},
            },
        }
        new = convert_legacy_config(old)
        name_mapping = new['reagent_selection']['selector_valves'].get('name_mapping', {})
        assert "port_1" in name_mapping
        assert "port_2" not in name_mapping
        assert "port_3" not in name_mapping
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/control/test_config.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/control/test_config.py
git commit -m "test: add unit tests for config loading and legacy conversion"
```

---

### Task 4: Unit tests for sequences.py

**Files:**
- Create: `software/tests/unit/test_sequences.py`
- Test: `software/fluidics/sequences.py`

**Step 1: Write tests**

```python
# tests/unit/test_sequences.py
import os
import tempfile

import pytest
import yaml
from pydantic import ValidationError

from fluidics.sequences import (
    APPLICATION_SEQUENCES,
    SEQUENCE_TYPES,
    SEQUENCE_TYPE_LABELS,
    SequenceListAdapter,
    load_sequences,
    save_sequences_yaml,
    get_included_sequences,
    get_fields_for_type,
)


class TestSequenceModels:
    def test_flow_reagent_valid(self):
        seq = SequenceListAdapter.validate_python([
            {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000, "volume": 2000}
        ])
        assert seq[0].type == "flow_reagent"
        assert seq[0].repeat == 1  # default
        assert seq[0].include is True  # default
        assert seq[0].incubation_time == 0  # default

    def test_set_temperature_valid(self):
        seq = SequenceListAdapter.validate_python([
            {"type": "set_temperature", "temperature": 37.5}
        ])
        assert seq[0].temperature == 37.5

    def test_set_temperature_no_fluidic_fields(self):
        """set_temperature shouldn't accept fluidic_port."""
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([
                {"type": "set_temperature", "temperature": 37, "fluidic_port": 1}
            ])

    def test_unknown_type_rejected(self):
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([
                {"type": "nonexistent", "fluidic_port": 1, "flow_rate": 100, "volume": 100}
            ])

    def test_extra_fields_rejected(self):
        """extra='forbid' catches typos."""
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([
                {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000,
                 "volume": 2000, "typo_field": 123}
            ])

    def test_missing_required_field_rejected(self):
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([
                {"type": "flow_reagent", "fluidic_port": 1}  # missing flow_rate, volume
            ])

    def test_fill_tubing_with_optional(self):
        seq = SequenceListAdapter.validate_python([
            {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000, "volume": 2000}
        ])
        assert seq[0].fill_tubing_with is None

    def test_priming_no_fill_tubing_with(self):
        """Priming model doesn't have fill_tubing_with field."""
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([
                {"type": "priming", "fluidic_port": 1, "flow_rate": 5000,
                 "volume": 2000, "fill_tubing_with": 5}
            ])

    @pytest.mark.parametrize("field,value", [
        ("fluidic_port", 0),  # ge=1
        ("flow_rate", 0),     # gt=0
        ("volume", -1),       # gt=0
        ("repeat", 0),        # ge=1
        ("incubation_time", -1),  # ge=0
    ])
    def test_field_constraints(self, field, value):
        data = {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000, "volume": 2000}
        data[field] = value
        with pytest.raises(ValidationError):
            SequenceListAdapter.validate_python([data])


class TestSequenceLoadingYAML:
    def test_load_yaml(self, fixtures_dir):
        seqs = load_sequences(str(fixtures_dir / "valid_sequences.yaml"))
        assert len(seqs) > 0
        assert all("type" in s for s in seqs)

    def test_load_yaml_with_sequences_key(self, tmp_path):
        data = {"sequences": [
            {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 1000, "volume": 500}
        ]}
        path = tmp_path / "seqs.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(data, f)
        seqs = load_sequences(str(path))
        assert len(seqs) == 1

    def test_load_yaml_bare_list(self, tmp_path):
        data = [{"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 1000, "volume": 500}]
        path = tmp_path / "seqs.yaml"
        with open(path, "w") as f:
            yaml.safe_dump(data, f)
        seqs = load_sequences(str(path))
        assert len(seqs) == 1

    def test_load_empty_yaml(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        seqs = load_sequences(str(path))
        assert seqs == []

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            load_sequences("file.txt")


class TestSequenceLoadingCSV:
    def test_load_csv(self, fixtures_dir):
        seqs = load_sequences(str(fixtures_dir / "legacy_sequences.csv"))
        assert len(seqs) > 0
        types = [s["type"] for s in seqs]
        assert "flow_reagent" in types

    def test_csv_set_temperature_parsed(self, fixtures_dir):
        seqs = load_sequences(str(fixtures_dir / "legacy_sequences.csv"))
        temp_seqs = [s for s in seqs if s["type"] == "set_temperature"]
        assert len(temp_seqs) == 1
        assert temp_seqs[0]["temperature"] == 50.0


class TestSaveSequences:
    def test_round_trip(self, tmp_path):
        original = [
            {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 5000, "volume": 2000,
             "fill_tubing_with": 10, "incubation_time": 3},
            {"type": "set_temperature", "temperature": 37},
        ]
        path = str(tmp_path / "out.yaml")
        save_sequences_yaml(original, path)
        loaded = load_sequences(path)
        assert loaded[0]["type"] == "flow_reagent"
        assert loaded[0]["fluidic_port"] == 1
        assert loaded[1]["type"] == "set_temperature"
        assert loaded[1]["temperature"] == 37

    def test_defaults_excluded(self, tmp_path):
        original = [
            {"type": "flow_reagent", "fluidic_port": 1, "flow_rate": 1000, "volume": 500}
        ]
        path = str(tmp_path / "out.yaml")
        save_sequences_yaml(original, path)
        with open(path) as f:
            raw = yaml.safe_load(f)
        seq = raw["sequences"][0]
        assert "repeat" not in seq
        assert "include" not in seq
        assert "incubation_time" not in seq


class TestSequenceUtilities:
    def test_get_included_sequences(self):
        seqs = [
            {"type": "flow_reagent", "include": True},
            {"type": "priming", "include": False},
            {"type": "clean_up"},  # default True
        ]
        result = get_included_sequences(seqs)
        assert len(result) == 2

    def test_get_fields_for_type(self):
        fields = get_fields_for_type("flow_reagent")
        assert "fluidic_port" in fields
        assert "fill_tubing_with" in fields
        assert "type" not in fields

    def test_get_fields_for_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown sequence type"):
            get_fields_for_type("nonexistent")


class TestRegistryConsistency:
    def test_all_labels_have_types(self):
        for type_key in SEQUENCE_TYPE_LABELS:
            assert type_key in SEQUENCE_TYPES

    def test_all_types_have_labels(self):
        for type_key in SEQUENCE_TYPES:
            assert type_key in SEQUENCE_TYPE_LABELS

    def test_application_sequences_are_valid_types(self):
        for app, seq_types in APPLICATION_SEQUENCES.items():
            for t in seq_types:
                assert t in SEQUENCE_TYPES, f"{t} not in SEQUENCE_TYPES"
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/test_sequences.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/test_sequences.py
git commit -m "test: add unit tests for sequence loading, validation, and save"
```

---

### Task 5: Unit tests for syringe_pump.py

**Files:**
- Create: `software/tests/unit/control/test_syringe_pump.py`
- Test: `software/fluidics/control/syringe_pump.py`

**Step 1: Write tests**

```python
# tests/unit/control/test_syringe_pump.py
import pytest
from fluidics.control.syringe_pump import SyringePump, SyringePumpSimulation


@pytest.fixture
def pump():
    """Create a SyringePumpSimulation for testing pure-logic methods.

    SyringePumpSimulation.flow_rate_to_speed_code returns a fixed value,
    so we use the real SyringePump class method via the SPEED_SEC_MAPPING.
    """
    # We test the algorithm using the class-level mapping directly
    return None  # Tests use class methods / standalone logic


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
        """Every speed code from limit to 40 should be reachable by some flow rate."""
        pump_sim.speed_code_limit = 0
        seen = set()
        mapping = SyringePump.SPEED_SEC_MAPPING
        for i in range(len(mapping)):
            rate = pump_sim.volume * 60 / (mapping[i] * 1000)
            code = pump_sim.flow_rate_to_speed_code(rate)
            seen.add(code)
        # At minimum we should cover a good range
        assert len(seen) >= 20


class TestGetFlowRate:
    def test_known_values(self):
        """get_flow_rate is the inverse: volume * 60 / (mapping[code] * 1000)."""
        p = SyringePumpSimulation(sn=None, syringe_ul=5000, speed_code_limit=10, waste_port=1)
        # speed code 0 -> 1.25 sec -> 5000*60/(1.25*1000) = 240.0
        assert p.get_flow_rate(0) == 240.0
        # speed code 40 -> 600.0 sec -> 5000*60/(600*1000) = 0.5
        assert p.get_flow_rate(40) == 0.5

    def test_flow_rate_speed_code_consistency(self):
        """get_flow_rate(code) should approximately invert flow_rate_to_speed_code."""
        p = SyringePumpSimulation(sn=None, syringe_ul=5000, speed_code_limit=0, waste_port=1)
        p.speed_code_limit = 0
        p.flow_rate_to_speed_code = SyringePump.flow_rate_to_speed_code.__get__(p)
        for code in range(41):
            rate = p.get_flow_rate(code)
            recovered_code = p.flow_rate_to_speed_code(rate)
            assert recovered_code == code, f"Round-trip failed for code {code}: rate={rate}, recovered={recovered_code}"
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/control/test_syringe_pump.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/control/test_syringe_pump.py
git commit -m "test: add unit tests for syringe pump speed code algorithm"
```

---

### Task 6: Unit tests for controller.py utilities

**Files:**
- Create: `software/tests/unit/control/test_controller.py`
- Test: `software/fluidics/control/controller.py` (utility functions only)

**Step 1: Write tests**

```python
# tests/unit/control/test_controller.py
import numpy as np
import pytest

from fluidics.control.controller import split_byte, uint_to_bytes
from fluidics.control._def import MCU_CONSTANTS


class TestSplitByte:
    def test_zero(self):
        assert split_byte(0x00) == (0, 0)

    def test_max(self):
        assert split_byte(0xFF) == (0x0F, 0x0F)

    def test_known_value(self):
        assert split_byte(0xAB) == (0x0A, 0x0B)

    def test_high_nibble_only(self):
        assert split_byte(0xF0) == (0x0F, 0x00)

    def test_low_nibble_only(self):
        assert split_byte(0x0F) == (0x00, 0x0F)


class TestUintToBytes:
    def test_zero_one_byte(self):
        assert uint_to_bytes(0, 1) == [np.uint8(0)]

    def test_zero_two_bytes(self):
        assert uint_to_bytes(0, 2) == [np.uint8(0), np.uint8(0)]

    def test_255_one_byte(self):
        assert uint_to_bytes(255, 1) == [np.uint8(255)]

    def test_256_two_bytes(self):
        result = uint_to_bytes(256, 2)
        assert result == [np.uint8(1), np.uint8(0)]

    def test_65535_two_bytes(self):
        result = uint_to_bytes(65535, 2)
        assert result == [np.uint8(255), np.uint8(255)]

    def test_overflow_raises(self):
        with pytest.raises(AssertionError, match="Overflow"):
            uint_to_bytes(256, 1)

    def test_four_bytes(self):
        result = uint_to_bytes(0x01020304, 4)
        assert result == [np.uint8(1), np.uint8(2), np.uint8(3), np.uint8(4)]


class TestRawToPsi:
    """Test the raw_to_psi conversion formula from get_mcu_status.

    Formula: (raw - output_min) * (p_max - p_min) / (output_max - output_min) + p_min
    With: output_min=0, output_max=16383, p_min=-15, p_max=15
    """

    @staticmethod
    def raw_to_psi(raw_pressure):
        return (
            (raw_pressure - MCU_CONSTANTS._output_min)
            * (MCU_CONSTANTS._p_max - MCU_CONSTANTS._p_min)
            / (MCU_CONSTANTS._output_max - MCU_CONSTANTS._output_min)
            + MCU_CONSTANTS._p_min
        )

    def test_min_raw_gives_min_psi(self):
        result = self.raw_to_psi(0)
        assert result == pytest.approx(-15.0)

    def test_max_raw_gives_max_psi(self):
        result = self.raw_to_psi(16383)
        assert result == pytest.approx(15.0)

    def test_midpoint_gives_zero_psi(self):
        result = self.raw_to_psi(16383 / 2)
        assert result == pytest.approx(0.0, abs=0.01)
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/control/test_controller.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/control/test_controller.py
git commit -m "test: add unit tests for controller utility functions"
```

---

### Task 7: Unit tests for selector_valve.py

**Files:**
- Create: `software/tests/unit/control/test_selector_valve.py`
- Test: `software/fluidics/control/selector_valve.py`

**Step 1: Write tests**

```python
# tests/unit/control/test_selector_valve.py
import pytest

from fluidics.control.config import load_config
from fluidics.control.controller import FluidControllerSimulation
from fluidics.control.selector_valve import SelectorValve, SelectorValveSystem


@pytest.fixture
def flow_cell_system(fixtures_dir):
    """SelectorValveSystem with 3 valves (flow cell config)."""
    config = load_config(str(fixtures_dir / "flow_cell_config.yaml"))
    fc = FluidControllerSimulation(serial_number="test")
    return SelectorValveSystem(fc, config)


@pytest.fixture
def open_chamber_system(fixtures_dir):
    """SelectorValveSystem with 1 valve (open chamber config)."""
    config = load_config(str(fixtures_dir / "open_chamber_config.yaml"))
    fc = FluidControllerSimulation(serial_number="test")
    return SelectorValveSystem(fc, config)


class TestSelectorValveSystemInit:
    def test_flow_cell_port_count(self, flow_cell_system):
        # 3 valves with 10 ports each: (10-1) + (10-1) + 10 = 28
        assert flow_cell_system.available_port_number == 28

    def test_open_chamber_port_count(self, open_chamber_system):
        # 1 valve with 10 ports: 10
        assert open_chamber_system.available_port_number == 10


class TestPortToReagent:
    def test_known_mapping(self, flow_cell_system):
        assert flow_cell_system.port_to_reagent(1) == "reagent x"
        assert flow_cell_system.port_to_reagent(25) == "buffer 1"

    def test_out_of_range_returns_none(self, flow_cell_system):
        assert flow_cell_system.port_to_reagent(999) is None

    def test_unmapped_port_returns_none(self, open_chamber_system):
        # port_2 has no name mapping in open chamber config
        assert open_chamber_system.port_to_reagent(2) is None


class TestTubingFluidAmounts:
    def test_flow_cell_tubing_to_valve(self, flow_cell_system):
        # Port 1 is on valve 0: common(800) + valve_0(0) = 800
        assert flow_cell_system.get_tubing_fluid_amount_to_valve(1) == 800
        # Port 10 is on valve 1: common(800) + valve_1(200) = 1000
        assert flow_cell_system.get_tubing_fluid_amount_to_valve(10) == 1000
        # Port 19 is on valve 2: common(800) + valve_2(340) = 1140
        assert flow_cell_system.get_tubing_fluid_amount_to_valve(19) == 1140

    def test_open_chamber_tubing_to_valve(self, open_chamber_system):
        # Single valve: common(300) + valve_0(0) = 300
        assert open_chamber_system.get_tubing_fluid_amount_to_valve(1) == 300

    def test_tubing_to_port(self, flow_cell_system):
        assert flow_cell_system.get_tubing_fluid_amount_to_port(1) == 700
        assert flow_cell_system.get_tubing_fluid_amount_to_port(10) == 600
        assert flow_cell_system.get_tubing_fluid_amount_to_port(19) == 450


class TestGetPortNames:
    def test_flow_cell_names_count(self, flow_cell_system):
        names = flow_cell_system.get_port_names()
        assert len(names) == 28

    def test_names_format(self, flow_cell_system):
        names = flow_cell_system.get_port_names()
        assert names[0] == "Port 1: reagent x"
        assert names[24] == "Port 25: buffer 1"

    def test_open_chamber_unmapped_port(self, open_chamber_system):
        names = open_chamber_system.get_port_names()
        # port_2 has no mapping -> just "Port 2: "
        assert names[1] == "Port 2: "


class TestOpenPort:
    def test_open_port_single_valve(self, open_chamber_system):
        open_chamber_system.open_port(5)
        assert open_chamber_system.get_current_port() == 5

    def test_open_port_multi_valve(self, flow_cell_system):
        flow_cell_system.open_port(1)
        assert flow_cell_system.get_current_port() == 1

        flow_cell_system.open_port(10)
        assert flow_cell_system.get_current_port() == 10

        flow_cell_system.open_port(19)
        assert flow_cell_system.get_current_port() == 19

    def test_open_port_out_of_range_noop(self, open_chamber_system):
        open_chamber_system.open_port(5)
        open_chamber_system.open_port(999)  # should do nothing
        assert open_chamber_system.get_current_port() == 5
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/control/test_selector_valve.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/control/test_selector_valve.py
git commit -m "test: add unit tests for selector valve system"
```

---

### Task 8: Unit tests for convert_config.py

**Files:**
- Create: `software/tests/unit/test_convert_config.py`
- Test: `software/convert_config.py`

**Step 1: Write tests**

```python
# tests/unit/test_convert_config.py
import json

import pytest
import yaml

from convert_config import convert_json_to_yaml
from fluidics.control.config import FluidicsConfig


class TestConvertJsonToYaml:
    def test_flow_cell_roundtrip(self, fixtures_dir, tmp_path):
        json_path = str(fixtures_dir / "legacy_flow_cell_config.json")
        yaml_path = str(tmp_path / "output.yaml")

        result_path = convert_json_to_yaml(json_path, yaml_path)

        assert result_path == yaml_path
        config = FluidicsConfig(**yaml.safe_load(open(yaml_path)))
        assert config.application == "Flow Cell"

    def test_open_chamber_roundtrip(self, fixtures_dir, tmp_path):
        json_path = str(fixtures_dir / "legacy_open_chamber_config.json")
        yaml_path = str(tmp_path / "output.yaml")

        result_path = convert_json_to_yaml(json_path, yaml_path)

        config = FluidicsConfig(**yaml.safe_load(open(yaml_path)))
        assert config.application == "Open Chamber"

    def test_default_output_path(self, fixtures_dir, tmp_path):
        """When yaml_path is None, output goes alongside the JSON file."""
        # Copy JSON fixture to tmp so we don't pollute fixtures dir
        import shutil
        src = fixtures_dir / "legacy_flow_cell_config.json"
        dst = tmp_path / "my_config.json"
        shutil.copy(src, dst)

        result = convert_json_to_yaml(str(dst))
        assert result == str(tmp_path / "my_config.yaml")
        assert (tmp_path / "my_config.yaml").exists()
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/unit/test_convert_config.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/unit/test_convert_config.py
git commit -m "test: add unit tests for config conversion CLI"
```

---

### Task 9: Integration tests for MERFISH operations

**Files:**
- Create: `software/tests/integration/conftest.py`
- Create: `software/tests/integration/test_merfish_operations.py`
- Test: `software/fluidics/merfish_operations.py`

**Step 1: Write shared integration conftest**

```python
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
```

**Step 2: Write MERFISH operations tests**

```python
# tests/integration/test_merfish_operations.py
import pytest

from fluidics.merfish_operations import MERFISHOperations
from fluidics.experiment_worker import OperationError


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
```

**Step 3: Run tests**

Run: `cd software && python -m pytest tests/integration/test_merfish_operations.py -v`
Expected: all pass

**Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test: add integration tests for MERFISH operations"
```

---

### Task 10: Integration tests for Open Chamber operations

**Files:**
- Create: `software/tests/integration/test_open_chamber_operations.py`
- Test: `software/fluidics/open_chamber_operations.py`

**Step 1: Write tests**

```python
# tests/integration/test_open_chamber_operations.py
import pytest

from fluidics.control.config import load_config
from fluidics.control.controller import FluidControllerSimulation
from fluidics.control.disc_pump import DiscPump
from fluidics.control.selector_valve import SelectorValveSystem
from fluidics.control.syringe_pump import SyringePumpSimulation
from fluidics.control.temperature_controller import TCMControllerSimulation
from fluidics.open_chamber_operations import OpenChamberOperations


@pytest.fixture
def oc_ops(fixtures_dir):
    config = load_config(str(fixtures_dir / "open_chamber_config.yaml"))
    fc = FluidControllerSimulation(serial_number="test")
    sp = SyringePumpSimulation(
        sn=None,
        syringe_ul=config.syringe_pump.volume_ul,
        speed_code_limit=config.syringe_pump.speed_code_limit,
        waste_port=config.syringe_pump.waste_port,
    )
    sv = SelectorValveSystem(fc, config)
    dp = DiscPump(fc)
    tc = TCMControllerSimulation()
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
```

**Step 2: Run tests**

Run: `cd software && python -m pytest tests/integration/test_open_chamber_operations.py -v`
Expected: all pass

**Step 3: Commit**

```bash
git add tests/integration/test_open_chamber_operations.py
git commit -m "test: add integration tests for open chamber operations"
```

---

### Task 11: Update README with test instructions

**Files:**
- Modify: `README.md`
- Modify: `software/CLAUDE.md`

**Step 1: Add testing section to README.md**

Add after the "Getting Started" section:

```markdown
### Tests

Requires pytest: `pip install pytest`

```bash
cd software
python -m pytest                       # Run all unit + integration tests
python -m pytest tests/unit            # Unit tests only (fast, no hardware)
python -m pytest tests/integration     # Integration tests (uses simulation classes)
python -m pytest -v                    # Verbose output
```

Hardware tests in `tests/hardware/` require connected devices and are excluded from the default test run.
```

**Step 2: Update software/CLAUDE.md test commands**

Update the commands section to include pytest.

**Step 3: Commit**

```bash
git add README.md software/CLAUDE.md
git commit -m "docs: add test running instructions to README"
```

---

### Task 12: Final verification

**Step 1: Run full test suite**

Run: `cd software && python -m pytest -v`
Expected: all tests pass

**Step 2: Verify hardware tests are excluded**

Run: `cd software && python -m pytest --collect-only`
Expected: no tests from `tests/hardware/` collected

**Step 3: Final commit (if any fixups needed)**
