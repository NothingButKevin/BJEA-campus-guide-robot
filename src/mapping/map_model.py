"""地图数据结构与线程安全状态快照。"""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from time import time
from typing import Any


@dataclass
class Pose:
    """机器人在地图坐标系中的位姿，单位为米和度。"""

    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "yaw": self.yaw}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Pose":
        if not data:
            return cls()
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            yaw=float(data.get("yaw", 0.0)),
        )


@dataclass
class Waypoint:
    """地图内路径点。"""

    name: str
    x: float
    y: float
    yaw: float = 0.0

    def as_dict(self) -> dict[str, float | str]:
        return {"name": self.name, "x": self.x, "y": self.y, "yaw": self.yaw}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Waypoint":
        return cls(
            name=str(data["name"]),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            yaw=float(data.get("yaw", 0.0)),
        )


@dataclass
class PointMap:
    """可持久化的二维点云地图。"""

    name: str
    points: list[tuple[float, float]] = field(default_factory=list)
    pose: Pose = field(default_factory=Pose)
    waypoints: dict[str, Waypoint] = field(default_factory=dict)
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    metadata: dict[str, Any] = field(default_factory=dict)
    initialized: bool = False
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def add_waypoint(self, name: str) -> Waypoint:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("waypoint 名称不能为空")
        with self._lock:
            waypoint = Waypoint(clean_name, self.pose.x, self.pose.y, self.pose.yaw)
            self.waypoints[clean_name] = waypoint
            self.updated_at = time()
            return waypoint

    def delete_waypoint(self, name: str) -> bool:
        with self._lock:
            existed = self.waypoints.pop(name.strip(), None) is not None
            if existed:
                self.updated_at = time()
            return existed

    def snapshot(self, max_points: int | None = None) -> dict[str, Any]:
        """返回给 HTTP/UI 使用的线程安全快照。"""
        with self._lock:
            points = self.points
            if max_points and len(points) > max_points:
                step = max(1, len(points) // max_points)
                points = points[::step][:max_points]
            return {
                "name": self.name,
                "initialized": self.initialized,
                "pose": self.pose.as_dict(),
                "current_pose": self.pose.as_dict(),
                "points": [{"x": x, "y": y} for x, y in points],
                "waypoints": [wp.as_dict() for wp in self.waypoints.values()],
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "metadata": dict(self.metadata),
            }

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "created_at": self.created_at,
                "updated_at": time(),
                "points": [{"x": x, "y": y} for x, y in self.points],
                "pose": self.pose.as_dict(),
                "current_pose": self.pose.as_dict(),
                "waypoints": [wp.as_dict() for wp in self.waypoints.values()],
                "metadata": dict(self.metadata),
                "initialized": self.initialized,
            }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PointMap":
        points = [
            (float(p.get("x", 0.0)), float(p.get("y", 0.0)))
            for p in data.get("points", [])
        ]
        waypoints = {
            wp["name"]: Waypoint.from_dict(wp)
            for wp in data.get("waypoints", [])
            if "name" in wp
        }
        return cls(
            name=str(data["name"]),
            points=points,
            pose=Pose.from_dict(data.get("current_pose") or data.get("pose")),
            waypoints=waypoints,
            created_at=float(data.get("created_at", time())),
            updated_at=float(data.get("updated_at", time())),
            metadata=dict(data.get("metadata", {})),
            initialized=bool(data.get("initialized", bool(points))),
        )
