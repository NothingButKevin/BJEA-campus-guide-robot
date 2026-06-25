"""地图文件持久化。"""

from __future__ import annotations

import json
import re
from threading import RLock
from pathlib import Path

from .map_model import PointMap


_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]+")


def sanitize_map_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name.strip())
    cleaned = cleaned.strip("._ ")
    if not cleaned:
        raise ValueError("地图名称不能为空")
    return cleaned


class MapStorage:
    """按单文件 JSON 保存地图。"""

    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def list_maps(self) -> list[str]:
        return sorted(path.stem for path in self.directory.glob("*.json"))

    def path_for(self, name: str) -> Path:
        return self.directory / f"{sanitize_map_name(name)}.json"

    def exists(self, name: str) -> bool:
        return self.path_for(name).exists()

    def load(self, name: str) -> PointMap:
        path = self.path_for(name)
        with path.open("r", encoding="utf-8") as f:
            return PointMap.from_dict(json.load(f))

    def create(self, name: str) -> PointMap:
        return PointMap(name=sanitize_map_name(name))

    def save(self, point_map: PointMap) -> Path:
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            path = self.path_for(point_map.name)
            tmp_path = path.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(point_map.to_dict(), f, ensure_ascii=False, indent=2)
                f.write("\n")
            tmp_path.replace(path)
            return path
