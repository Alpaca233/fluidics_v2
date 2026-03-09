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
