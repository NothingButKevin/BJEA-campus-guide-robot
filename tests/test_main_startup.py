import builtins
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import _select_navigation_map
from mapping.storage import MapStorage


def _write_config(path: Path, maps_dir: Path):
    path.write_text(yaml.safe_dump({"mapping": {"maps_dir": str(maps_dir)}}), encoding="utf-8")


def test_navigation_map_selection_exits_when_no_maps(tmp_path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, tmp_path / "maps")

    with pytest.raises(SystemExit):
        _select_navigation_map(str(config_path))


def test_navigation_map_selection_requires_choice(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    maps_dir = tmp_path / "maps"
    _write_config(config_path, maps_dir)
    storage = MapStorage(maps_dir)
    storage.save(storage.create("main"))
    monkeypatch.setattr(builtins, "input", lambda _: "")

    with pytest.raises(SystemExit):
        _select_navigation_map(str(config_path))


def test_navigation_map_selection_loads_numbered_map(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    maps_dir = tmp_path / "maps"
    _write_config(config_path, maps_dir)
    storage = MapStorage(maps_dir)
    storage.save(storage.create("main"))
    monkeypatch.setattr(builtins, "input", lambda _: "1")

    selected = _select_navigation_map(str(config_path))

    assert selected.name == "main"
