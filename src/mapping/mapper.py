"""快照拼接式二维点云地图。"""

from __future__ import annotations

import logging
import math
import statistics
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
from scipy.spatial import cKDTree

from .map_model import PointMap, Pose
from .storage import MapStorage

logger = logging.getLogger(__name__)

PolarPoint = tuple[float, float, int]
XYPoint = tuple[float, float]


def _angle_in_range(angle: float, start: float, end: float) -> bool:
    if abs(end - start) >= 360.0:
        return True
    angle %= 360.0
    start %= 360.0
    end %= 360.0
    if start <= end:
        return start <= angle <= end
    return angle >= start or angle <= end


def polar_to_robot_xy(angle_deg: float, distance_m: float, horizontal_flip: bool = True) -> XYPoint:
    """LD06 角度转机器人局部坐标。

    约定：270 度为机器人正前方 +x。倒立安装默认水平翻转左右方向。
    """
    theta = math.radians(270.0 - angle_deg)
    x = distance_m * math.cos(theta)
    y = distance_m * math.sin(theta)
    return x, -y if horizontal_flip else y


def transform_points(points: Iterable[XYPoint], pose: Pose) -> list[XYPoint]:
    yaw = math.radians(pose.yaw)
    cos_yaw = math.cos(yaw)
    sin_yaw = math.sin(yaw)
    return [
        (
            pose.x + x * cos_yaw - y * sin_yaw,
            pose.y + x * sin_yaw + y * cos_yaw,
        )
        for x, y in points
    ]


@dataclass
class MatchResult:
    pose: Pose
    accepted: bool
    overlap_ratio: float = 0.0
    mean_error_m: float = 999.0
    message: str = ""
    ambiguous: bool = False
    candidates: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "pose": self.pose.as_dict(),
            "accepted": self.accepted,
            "overlap_ratio": self.overlap_ratio,
            "mean_error_m": self.mean_error_m,
            "message": self.message,
            "ambiguous": self.ambiguous,
            "candidates": self.candidates,
        }


@dataclass
class MapperStatus:
    state: str = "idle"
    last_error: str = ""
    last_snapshot_points: int = 0
    last_update_time: float = 0.0
    snapshot_seq: int = 0
    last_match: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "last_error": self.last_error,
            "last_snapshot_points": self.last_snapshot_points,
            "last_update_time": self.last_update_time,
            "snapshot_seq": self.snapshot_seq,
            "last_match": self.last_match,
        }


@dataclass
class MapperConfig:
    angle_min: float = 0.0
    angle_max: float = 360.0
    min_distance_m: float = 0.08
    max_distance_m: float = 10.0
    robot_body_radius_m: float = 0.60
    horizontal_flip: bool = True
    grid_resolution_m: float = 0.05
    snapshot_duration_s: float = 1.0
    snapshot_revolutions: int = 5
    snapshot_min_scan_timeout_s: float = 0.25
    snapshot_min_consensus_ratio: float = 0.60
    snapshot_bucket_deg: float = 1.0
    snapshot_consensus_angle_window_deg: float = 1.0
    snapshot_distance_tolerance_m: float = 0.30
    snapshot_distance_tolerance_ratio: float = 0.12
    max_points: int = 80000
    autosave_interval_s: float = 5.0
    coarse_search_xy_m: float = 1.0
    coarse_search_xy_step_m: float = 0.10
    coarse_search_yaw_deg: float = 45.0
    coarse_search_yaw_step_deg: float = 5.0
    icp_iterations: int = 12
    icp_inlier_distance_m: float = 0.18
    max_icp_yaw_correction_deg: float = 20.0
    global_yaw_step_deg: float = 10.0
    local_refine_yaw_deg: float = 6.0
    local_refine_yaw_step_deg: float = 1.0
    local_refine_xy_m: float = 0.10
    local_refine_xy_step_m: float = 0.05
    vote_resolution_m: float = 0.20
    vote_top_per_yaw: int = 3
    candidate_top_k: int = 8
    trim_fraction: float = 0.40
    match_density_resolution_m: float = 0.15
    min_inlier_short_axis_m: float = 0.25
    min_inlier_axis_ratio: float = 0.08
    ambiguity_score_gap: float = 0.15
    min_overlap_ratio: float = 0.25
    max_mean_error_m: float = 0.16
    min_snapshot_points: int = 40

    @classmethod
    def from_dict(cls, data: dict) -> "MapperConfig":
        return cls(
            angle_min=float(data.get("angle_min", 0.0)),
            angle_max=float(data.get("angle_max", 360.0)),
            min_distance_m=float(data.get("min_distance_m", 0.08)),
            max_distance_m=float(data.get("max_distance_m", 10.0)),
            robot_body_radius_m=float(data.get("robot_body_radius_m", 0.60)),
            horizontal_flip=bool(data.get("horizontal_flip", True)),
            grid_resolution_m=float(data.get("grid_resolution_m", 0.05)),
            snapshot_duration_s=float(data.get("snapshot_duration_s", 1.0)),
            snapshot_revolutions=int(data.get("snapshot_revolutions", 5)),
            snapshot_min_scan_timeout_s=float(data.get("snapshot_min_scan_timeout_s", 0.25)),
            snapshot_min_consensus_ratio=float(data.get("snapshot_min_consensus_ratio", 0.60)),
            snapshot_bucket_deg=float(data.get("snapshot_bucket_deg", 1.0)),
            snapshot_consensus_angle_window_deg=float(data.get("snapshot_consensus_angle_window_deg", 1.0)),
            snapshot_distance_tolerance_m=float(data.get("snapshot_distance_tolerance_m", 0.30)),
            snapshot_distance_tolerance_ratio=float(data.get("snapshot_distance_tolerance_ratio", 0.12)),
            max_points=int(data.get("max_points", 80000)),
            autosave_interval_s=float(data.get("autosave_interval_s", 5.0)),
            coarse_search_xy_m=float(data.get("coarse_search_xy_m", 1.0)),
            coarse_search_xy_step_m=float(data.get("coarse_search_xy_step_m", 0.10)),
            coarse_search_yaw_deg=float(data.get("coarse_search_yaw_deg", 45.0)),
            coarse_search_yaw_step_deg=float(data.get("coarse_search_yaw_step_deg", 5.0)),
            icp_iterations=int(data.get("icp_iterations", 12)),
            icp_inlier_distance_m=float(data.get("icp_inlier_distance_m", 0.18)),
            max_icp_yaw_correction_deg=float(data.get("max_icp_yaw_correction_deg", 20.0)),
            global_yaw_step_deg=float(data.get("global_yaw_step_deg", 10.0)),
            local_refine_yaw_deg=float(data.get("local_refine_yaw_deg", 6.0)),
            local_refine_yaw_step_deg=float(data.get("local_refine_yaw_step_deg", 1.0)),
            local_refine_xy_m=float(data.get("local_refine_xy_m", 0.10)),
            local_refine_xy_step_m=float(data.get("local_refine_xy_step_m", 0.05)),
            vote_resolution_m=float(data.get("vote_resolution_m", 0.20)),
            vote_top_per_yaw=int(data.get("vote_top_per_yaw", 3)),
            candidate_top_k=int(data.get("candidate_top_k", 8)),
            trim_fraction=float(data.get("trim_fraction", 0.40)),
            match_density_resolution_m=float(data.get("match_density_resolution_m", 0.15)),
            min_inlier_short_axis_m=float(data.get("min_inlier_short_axis_m", 0.25)),
            min_inlier_axis_ratio=float(data.get("min_inlier_axis_ratio", 0.08)),
            ambiguity_score_gap=float(data.get("ambiguity_score_gap", 0.15)),
            min_overlap_ratio=float(data.get("min_overlap_ratio", 0.25)),
            max_mean_error_m=float(data.get("max_mean_error_m", 0.16)),
            min_snapshot_points=int(data.get("min_snapshot_points", 40)),
        )


class SnapshotCollector:
    """从 LD06 多帧数据生成稳定 360 度快照。"""

    def __init__(self, lidar, config: MapperConfig):
        self.lidar = lidar
        self.config = config

    def collect(self) -> list[XYPoint]:
        flush_input = getattr(self.lidar, "flush_input", None)
        if callable(flush_input):
            flush_input()

        revolutions = max(1, self.config.snapshot_revolutions)
        timeout = max(self.config.snapshot_min_scan_timeout_s, self.config.snapshot_duration_s / revolutions)
        scans: list[dict[int, float]] = []
        for _ in range(revolutions):
            scan = self.lidar.read_scan(timeout=timeout)
            scan_buckets: dict[int, list[float]] = {}
            for angle, distance_m, confidence in scan:
                bucket = self._bucket_scan_point(angle, distance_m)
                if bucket is None:
                    continue
                scan_buckets.setdefault(bucket, []).append(distance_m)
            scans.append({
                bucket: statistics.median(values)
                for bucket, values in scan_buckets.items()
                if values
            })

        points: list[XYPoint] = []
        if not scans:
            return points
        all_buckets = sorted({bucket for scan in scans for bucket in scan})
        accepted_buckets: set[int] = set()
        min_observations = max(1, math.ceil(revolutions * min(max(self.config.snapshot_min_consensus_ratio, 0.0), 1.0)))
        for bucket in all_buckets:
            if bucket in accepted_buckets:
                continue
            distances = self._consensus_distances(bucket, scans)
            if len(distances) < min_observations:
                continue
            distance = statistics.median(distances)
            tolerance = max(
                self.config.snapshot_distance_tolerance_m,
                abs(distance) * self.config.snapshot_distance_tolerance_ratio,
            )
            stable = [value for value in distances if abs(value - distance) <= tolerance]
            if len(stable) < min_observations:
                continue
            distance = statistics.median(stable)
            accepted_buckets.add(bucket)
            angle = bucket * self.config.snapshot_bucket_deg
            points.append(polar_to_robot_xy(angle, distance, self.config.horizontal_flip))
        return points

    def _bucket_scan_point(self, angle: float, distance_m: float) -> int | None:
        if not _angle_in_range(angle, self.config.angle_min, self.config.angle_max):
            return None
        if distance_m < max(self.config.min_distance_m, self.config.robot_body_radius_m):
            return None
        if distance_m > self.config.max_distance_m:
            return None
        return round((angle % 360.0) / max(self.config.snapshot_bucket_deg, 0.1))

    def _consensus_distances(self, bucket: int, scans: list[dict[int, float]]) -> list[float]:
        window = round(self.config.snapshot_consensus_angle_window_deg / max(self.config.snapshot_bucket_deg, 0.1))
        distances: list[float] = []
        for scan in scans:
            candidates = [
                (abs(other - bucket), distance)
                for other, distance in scan.items()
                if abs(other - bucket) <= window
            ]
            if not candidates:
                continue
            _, distance = min(candidates, key=lambda item: item[0])
            distances.append(distance)
        return distances


class SnapshotMatcher:
    """把局部快照点云匹配到全局点云地图。"""

    def __init__(self, config: MapperConfig):
        self.config = config

    def match(self, local_points: list[XYPoint], map_points: list[XYPoint], guess: Pose) -> MatchResult:
        if len(local_points) < self.config.min_snapshot_points:
            return MatchResult(guess, False, message="快照有效点过少")
        if not map_points:
            return MatchResult(Pose(0.0, 0.0, 0.0), True, 1.0, 0.0, "第一张快照")

        source = self._normalize_density(self._to_array(local_points))
        target = self._normalize_density(self._to_array(map_points))
        if len(source) < self.config.min_snapshot_points or len(target) < self.config.min_snapshot_points:
            return MatchResult(guess, False, message="地图或快照有效点过少")

        initial_candidates = self._global_vote_candidates(source, target)
        if not initial_candidates:
            return MatchResult(guess, False, message="全局搜索未找到候选")

        target_tree = cKDTree(target)
        refined = []
        for candidate in initial_candidates:
            pose, overlap, mean_error, geometry = self._trimmed_icp(source, target, target_tree, candidate)
            pose, overlap, mean_error, geometry = self._local_refine(source, target_tree, pose)
            score = self._score(overlap, mean_error, geometry)
            refined.append((score, pose, overlap, mean_error, geometry))

        refined.sort(key=lambda item: item[0], reverse=True)
        best_score, best_pose, best_overlap, best_error, best_geometry = refined[0]
        candidate_dicts = [
            {
                "rank": idx + 1,
                "score": round(score, 6),
                "pose": pose.as_dict(),
                "overlap_ratio": overlap,
                "mean_error_m": error,
                "geometry": geometry,
            }
            for idx, (score, pose, overlap, error, geometry) in enumerate(refined[: self.config.candidate_top_k])
        ]

        geometry_ok = bool(best_geometry.get("accepted", False))
        quality_ok = (
            best_overlap >= self.config.min_overlap_ratio
            and best_error <= self.config.max_mean_error_m
            and geometry_ok
        )
        ambiguous = False
        if len(refined) > 1 and quality_ok:
            second_score = refined[1][0]
            if second_score > 0:
                ambiguous = (best_score - second_score) / max(abs(best_score), 1e-9) < self.config.ambiguity_score_gap

        if not quality_ok:
            return MatchResult(
                best_pose,
                False,
                best_overlap,
                best_error,
                "匹配失败：重合率、误差或几何覆盖不达标",
                candidates=candidate_dicts,
            )
        if ambiguous:
            return MatchResult(
                best_pose,
                False,
                best_overlap,
                best_error,
                "匹配歧义：多个候选过于接近，请人工确认",
                ambiguous=True,
                candidates=candidate_dicts,
            )
        return MatchResult(best_pose, True, best_overlap, best_error, "匹配成功", candidates=candidate_dicts)

    def _global_vote_candidates(self, source: np.ndarray, target: np.ndarray) -> list[Pose]:
        source_sample = self._sample_array(source, 140)
        target_sample = self._sample_array(target, 700)
        yaw_step = max(self.config.global_yaw_step_deg, 1.0)
        vote_res = max(self.config.vote_resolution_m, 0.02)
        top_per_yaw = max(1, self.config.vote_top_per_yaw)
        raw_candidates: list[tuple[int, Pose]] = []

        for yaw in self._float_range(0.0, 360.0 - yaw_step, yaw_step):
            rotated = self._rotate_array(source_sample, yaw)
            votes: dict[tuple[int, int], int] = {}
            for sx, sy in rotated:
                deltas = target_sample - np.array([sx, sy])
                cells = np.rint(deltas / vote_res).astype(np.int32)
                for cx, cy in cells:
                    key = (int(cx), int(cy))
                    votes[key] = votes.get(key, 0) + 1
            for (cx, cy), count in sorted(votes.items(), key=lambda item: item[1], reverse=True)[:top_per_yaw]:
                raw_candidates.append((count, Pose(cx * vote_res, cy * vote_res, yaw)))

        raw_candidates.sort(key=lambda item: item[0], reverse=True)
        unique: list[Pose] = []
        for _, pose in raw_candidates:
            if any(self._pose_near(pose, seen) for seen in unique):
                continue
            unique.append(pose)
            if len(unique) >= self.config.candidate_top_k:
                break
        return unique

    def _trimmed_icp(
        self,
        source: np.ndarray,
        target: np.ndarray,
        target_tree: cKDTree,
        initial: Pose,
    ) -> tuple[Pose, float, float, dict]:
        pose = initial
        source_sample = self._sample_array(source, 320)
        trim_count = max(8, int(len(source_sample) * min(max(self.config.trim_fraction, 0.1), 1.0)))

        for _ in range(max(1, self.config.icp_iterations)):
            transformed = self._transform_array(source_sample, pose)
            distances, indices = target_tree.query(transformed, k=1)
            order = np.argsort(distances)[:trim_count]
            if len(order) < 8:
                break
            pose = self._fit_arrays(source_sample[order], target[indices[order]], pose)

        transformed = self._transform_array(source_sample, pose)
        distances, _ = target_tree.query(transformed, k=1)
        inliers = distances <= self.config.icp_inlier_distance_m
        overlap = float(np.count_nonzero(inliers)) / max(1, len(source_sample))
        mean_error = float(np.mean(distances[inliers])) if np.any(inliers) else 999.0
        geometry = self._inlier_geometry(transformed[inliers])
        return pose, overlap, mean_error, geometry

    def _local_refine(self, source: np.ndarray, target_tree: cKDTree, initial: Pose) -> tuple[Pose, float, float, dict]:
        source_sample = self._sample_array(source, 320)
        best_pose = initial
        best_overlap, best_error, best_geometry = self._evaluate_pose(source_sample, target_tree, initial)
        best_score = self._score(best_overlap, best_error, best_geometry)

        yaw_radius = max(0.0, self.config.local_refine_yaw_deg)
        yaw_step = max(0.1, self.config.local_refine_yaw_step_deg)
        xy_radius = max(0.0, self.config.local_refine_xy_m)
        xy_step = max(0.01, self.config.local_refine_xy_step_m)

        for dyaw in self._float_range(-yaw_radius, yaw_radius, yaw_step):
            for dx in self._float_range(-xy_radius, xy_radius, xy_step):
                for dy in self._float_range(-xy_radius, xy_radius, xy_step):
                    pose = Pose(initial.x + dx, initial.y + dy, (initial.yaw + dyaw) % 360.0)
                    overlap, error, geometry = self._evaluate_pose(source_sample, target_tree, pose)
                    score = self._score(overlap, error, geometry)
                    if score > best_score:
                        best_score = score
                        best_pose = pose
                        best_overlap = overlap
                        best_error = error
                        best_geometry = geometry
        return best_pose, best_overlap, best_error, best_geometry

    def _evaluate_pose(self, source: np.ndarray, target_tree: cKDTree, pose: Pose) -> tuple[float, float, dict]:
        transformed = self._transform_array(source, pose)
        distances, _ = target_tree.query(transformed, k=1)
        inliers = distances <= self.config.icp_inlier_distance_m
        overlap = float(np.count_nonzero(inliers)) / max(1, len(source))
        mean_error = float(np.mean(distances[inliers])) if np.any(inliers) else 999.0
        geometry = self._inlier_geometry(transformed[inliers])
        return overlap, mean_error, geometry

    def _score(self, overlap: float, mean_error: float, geometry: dict) -> float:
        if mean_error >= 999.0:
            return 0.0
        score = overlap / (0.02 + mean_error)
        if not geometry.get("accepted", False):
            score *= 0.10
        return score

    def _inlier_geometry(self, points: np.ndarray) -> dict:
        if len(points) < 3:
            return {
                "short_axis_m": 0.0,
                "long_axis_m": 0.0,
                "axis_ratio": 0.0,
                "bbox_area_m2": 0.0,
                "accepted": False,
            }
        centered = points - np.mean(points, axis=0)
        covariance = centered.T @ centered / max(1, len(points) - 1)
        eigvals = np.linalg.eigvalsh(covariance)
        eigvals = np.maximum(eigvals, 0.0)
        short_axis = float(math.sqrt(eigvals[0]))
        long_axis = float(math.sqrt(eigvals[1]))
        axis_ratio = short_axis / max(long_axis, 1e-9)
        mins = np.min(points, axis=0)
        maxs = np.max(points, axis=0)
        bbox_area = float(max(0.0, maxs[0] - mins[0]) * max(0.0, maxs[1] - mins[1]))
        accepted = (
            short_axis >= self.config.min_inlier_short_axis_m
            and axis_ratio >= self.config.min_inlier_axis_ratio
        )
        return {
            "short_axis_m": short_axis,
            "long_axis_m": long_axis,
            "axis_ratio": axis_ratio,
            "bbox_area_m2": bbox_area,
            "accepted": accepted,
        }

    @staticmethod
    def _pose_near(a: Pose, b: Pose) -> bool:
        yaw_delta = abs(((a.yaw - b.yaw + 180.0) % 360.0) - 180.0)
        return math.hypot(a.x - b.x, a.y - b.y) < 0.15 and yaw_delta < 2.0

    @staticmethod
    def _to_array(points: list[XYPoint]) -> np.ndarray:
        return np.asarray(points, dtype=np.float64).reshape((-1, 2))

    @staticmethod
    def _rotate_array(points: np.ndarray, yaw_deg: float) -> np.ndarray:
        yaw = math.radians(yaw_deg)
        rot = np.array([[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]])
        return points @ rot.T

    def _transform_array(self, points: np.ndarray, pose: Pose) -> np.ndarray:
        return self._rotate_array(points, pose.yaw) + np.array([pose.x, pose.y])

    @staticmethod
    def _sample_array(points: np.ndarray, limit: int) -> np.ndarray:
        if len(points) <= limit:
            return points
        step = max(1, len(points) // limit)
        return points[::step][:limit]

    def _normalize_density(self, points: np.ndarray) -> np.ndarray:
        resolution = max(self.config.match_density_resolution_m, 0.01)
        return self._voxel_downsample_array(points, resolution)

    @staticmethod
    def _voxel_downsample_array(points: np.ndarray, resolution: float) -> np.ndarray:
        if len(points) == 0:
            return points
        cells = np.rint(points / max(resolution, 0.001)).astype(np.int64)
        _, indices = np.unique(cells, axis=0, return_index=True)
        indices.sort()
        return points[indices]

    def _fit_arrays(self, source: np.ndarray, target: np.ndarray, fallback: Pose) -> Pose:
        source_centroid = np.mean(source, axis=0)
        target_centroid = np.mean(target, axis=0)
        centered_source = source - source_centroid
        centered_target = target - target_centroid
        covariance = centered_source.T @ centered_target
        try:
            u, _, vt = np.linalg.svd(covariance)
        except np.linalg.LinAlgError:
            return fallback
        rotation = vt.T @ u.T
        if np.linalg.det(rotation) < 0:
            vt[-1, :] *= -1
            rotation = vt.T @ u.T
        translation = target_centroid - rotation @ source_centroid
        yaw = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0])) % 360.0
        if not np.all(np.isfinite(translation)) or not math.isfinite(yaw):
            return fallback
        return Pose(float(translation[0]), float(translation[1]), yaw)

    def _coarse_match(self, local_points: list[XYPoint], map_points: list[XYPoint], guess: Pose) -> tuple[Pose, float]:
        grid = {self._cell(p) for p in map_points}
        sample = self._sample(local_points, 160)
        best_pose = guess
        best_score = -1.0

        for dx in self._float_range(-self.config.coarse_search_xy_m, self.config.coarse_search_xy_m, self.config.coarse_search_xy_step_m):
            for dy in self._float_range(-self.config.coarse_search_xy_m, self.config.coarse_search_xy_m, self.config.coarse_search_xy_step_m):
                for dyaw in self._float_range(-self.config.coarse_search_yaw_deg, self.config.coarse_search_yaw_deg, self.config.coarse_search_yaw_step_deg):
                    pose = Pose(guess.x + dx, guess.y + dy, (guess.yaw + dyaw) % 360.0)
                    transformed = transform_points(sample, pose)
                    hits = sum(1 for point in transformed if self._cell(point) in grid)
                    score = hits / max(1, len(sample))
                    if score > best_score:
                        best_score = score
                        best_pose = pose
        return best_pose, max(0.0, best_score)

    def _icp_refine(self, local_points: list[XYPoint], map_points: list[XYPoint], initial: Pose) -> tuple[Pose, float, float]:
        pose = initial
        yaw_anchor = initial.yaw
        source = self._sample(local_points, 220)
        target = self._sample(map_points, 2500)
        if not source or not target:
            return pose, 0.0, 999.0

        for _ in range(self.config.icp_iterations):
            transformed = transform_points(source, pose)
            pairs = []
            distances = []
            for src_local, src_global in zip(source, transformed):
                nearest, dist = self._nearest(src_global, target)
                if dist <= self.config.icp_inlier_distance_m:
                    pairs.append((src_local, nearest))
                    distances.append(dist)
            if len(pairs) < 8:
                break
            pose = self._fit_pose(pairs, pose, yaw_anchor)

        transformed = transform_points(source, pose)
        inliers = []
        for point in transformed:
            _, dist = self._nearest(point, target)
            if dist <= self.config.icp_inlier_distance_m:
                inliers.append(dist)
        overlap = len(inliers) / max(1, len(source))
        mean_error = sum(inliers) / len(inliers) if inliers else 999.0
        return pose, overlap, mean_error

    def _fit_pose(self, pairs: list[tuple[XYPoint, XYPoint]], fallback: Pose, yaw_anchor: float) -> Pose:
        src_centroid = self._centroid([p[0] for p in pairs])
        dst_centroid = self._centroid([p[1] for p in pairs])
        sxx = syy = sxy = syx = 0.0
        for src, dst in pairs:
            sx = src[0] - src_centroid[0]
            sy = src[1] - src_centroid[1]
            dx = dst[0] - dst_centroid[0]
            dy = dst[1] - dst_centroid[1]
            sxx += sx * dx
            syy += sy * dy
            sxy += sx * dy
            syx += sy * dx
        yaw = math.atan2(sxy - syx, sxx + syy)
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        tx = dst_centroid[0] - (src_centroid[0] * cos_yaw - src_centroid[1] * sin_yaw)
        ty = dst_centroid[1] - (src_centroid[0] * sin_yaw + src_centroid[1] * cos_yaw)
        if not all(math.isfinite(v) for v in (tx, ty, yaw)):
            return fallback
        fitted = Pose(tx, ty, math.degrees(yaw) % 360.0)
        delta = ((fitted.yaw - yaw_anchor + 180.0) % 360.0) - 180.0
        if abs(delta) > self.config.max_icp_yaw_correction_deg:
            fitted.yaw = yaw_anchor
        return fitted

    @staticmethod
    def _nearest(point: XYPoint, target: list[XYPoint]) -> tuple[XYPoint, float]:
        best = target[0]
        best_dist_sq = float("inf")
        px, py = point
        for tx, ty in target:
            dist_sq = (px - tx) ** 2 + (py - ty) ** 2
            if dist_sq < best_dist_sq:
                best = (tx, ty)
                best_dist_sq = dist_sq
        return best, math.sqrt(best_dist_sq)

    @staticmethod
    def _centroid(points: list[XYPoint]) -> XYPoint:
        return (
            sum(p[0] for p in points) / max(1, len(points)),
            sum(p[1] for p in points) / max(1, len(points)),
        )

    def _cell(self, point: XYPoint) -> tuple[int, int]:
        res = max(self.config.grid_resolution_m, 0.001)
        return (round(point[0] / res), round(point[1] / res))

    @staticmethod
    def _sample(points: list[XYPoint], limit: int) -> list[XYPoint]:
        if len(points) <= limit:
            return points
        step = max(1, len(points) // limit)
        return points[::step][:limit]

    @staticmethod
    def _float_range(start: float, stop: float, step: float) -> list[float]:
        values = []
        value = start
        while value <= stop + 1e-9:
            values.append(round(value, 6))
            value += step
        return values


class PointCloudMapper:
    """按需采集快照并拼接到全局二维点云地图。"""

    def __init__(self, point_map: PointMap, storage: MapStorage, config: MapperConfig, lidar=None):
        self.map = point_map
        self.storage = storage
        self.config = config
        self.lidar = lidar
        self.collector = SnapshotCollector(lidar, config) if lidar is not None else None
        self.matcher = SnapshotMatcher(config)
        self.status = MapperStatus()
        self.last_snapshot_preview: list[XYPoint] = []
        self.last_match: MatchResult | None = None
        self.pending_snapshot: list[XYPoint] = []
        self.pending_candidates: list[dict] = []
        self._grid: dict[tuple[int, int], XYPoint] = {}
        self._last_save = 0.0
        self._last_integration: dict | None = None
        self._capture_lock = threading.Lock()
        self._rebuild_grid()

    def capture_and_integrate(self, name: str = "", initial_pose: Pose | None = None) -> MatchResult:
        if self.collector is None:
            raise RuntimeError("雷达未初始化，无法采集快照")
        with self._capture_lock:
            self.status.state = "capturing"
            self.status.last_error = ""
            snapshot = self.collector.collect()
            return self.integrate_snapshot(snapshot, name=name, initial_pose=initial_pose)

    def integrate_snapshot(self, snapshot: list[XYPoint], name: str = "", initial_pose: Pose | None = None) -> MatchResult:
        self.status.snapshot_seq += 1
        self.status.last_snapshot_points = len(snapshot)
        self.status.last_update_time = time.time()

        guess = initial_pose or self.map.pose
        result = self.matcher.match(snapshot, list(self.map.points), guess)
        self.last_match = result
        self.status.last_match = result.as_dict()
        self.last_snapshot_preview = transform_points(snapshot, result.pose if result.accepted else guess)

        if not result.accepted:
            self.status.state = "match_failed"
            self.status.last_error = result.message
            if result.ambiguous:
                self.status.state = "ambiguous"
                self.pending_snapshot = list(snapshot)
                self.pending_candidates = self._candidates_with_preview(snapshot, result.candidates)
                result.candidates = self.pending_candidates
                self.status.last_match = result.as_dict()
            else:
                self.pending_snapshot = []
                self.pending_candidates = []
            return result

        with self.map._lock:
            self._last_integration = self._integrate_locked(snapshot, result.pose, name, result)
        self.status.state = "mapped"
        self.status.last_error = ""
        self.pending_snapshot = []
        self.pending_candidates = []
        self._autosave()
        return result

    def discard_pending_snapshot(self):
        with self._capture_lock:
            undone = False
            if self._last_integration is not None:
                with self.map._lock:
                    self._undo_last_integration_locked()
                undone = True
            self.pending_snapshot = []
            self.pending_candidates = []
            self.last_snapshot_preview = []
            self.last_match = None
            self.status.last_match = {}
            self.status.state = "discarded"
            self.status.last_error = "已撤销最近一次融合" if undone else ""
            if undone:
                self.save()
            return self.snapshot()

    def accept_candidate(self, rank: int, name: str = "") -> MatchResult:
        with self._capture_lock:
            if not self.pending_snapshot or not self.pending_candidates:
                raise ValueError("当前没有待确认候选")
            candidate = next((item for item in self.pending_candidates if int(item.get("rank", -1)) == rank), None)
            if candidate is None:
                raise ValueError(f"候选不存在: {rank}")
            pose = Pose.from_dict(candidate.get("pose"))
            result = MatchResult(
                pose=pose,
                accepted=True,
                overlap_ratio=float(candidate.get("overlap_ratio", 0.0)),
                mean_error_m=float(candidate.get("mean_error_m", 999.0)),
                message="已人工确认候选",
                candidates=self.pending_candidates,
            )
            with self.map._lock:
                self._last_integration = self._integrate_locked(self.pending_snapshot, pose, name, result)
            self.last_match = result
            self.status.last_match = result.as_dict()
            self.status.state = "mapped"
            self.status.last_error = ""
            self.last_snapshot_preview = transform_points(self.pending_snapshot, pose)
            self.pending_snapshot = []
            self.pending_candidates = []
            self._autosave()
            return result

    def add_waypoint(self, name: str):
        waypoint = self.map.add_waypoint(name)
        self.save()
        return waypoint

    def set_pose(self, pose: Pose):
        with self.map._lock:
            self.map.pose = pose
            self.map.updated_at = time.time()
        self.status.state = "pose_set"
        self.status.last_error = ""
        return pose

    def snapshot(self) -> dict:
        data = self.map.snapshot(max_points=12000)
        data["current_pose"] = data["pose"]
        data["last_snapshot_preview"] = [
            {"x": x, "y": y}
            for x, y in self.last_snapshot_preview[:2000]
        ]
        data["last_match"] = self.last_match.as_dict() if self.last_match else {}
        data["pending_candidates"] = list(self.pending_candidates)
        data["status"] = self.status.as_dict()
        return data

    def save(self):
        self.storage.save(self.map)
        self._last_save = time.time()

    def _merge_points(self, points: list[XYPoint]) -> list[tuple[tuple[int, int], XYPoint]]:
        added: list[tuple[tuple[int, int], XYPoint]] = []
        for point in points:
            cell = self._cell(point)
            if cell not in self._grid:
                rounded = (round(point[0], 3), round(point[1], 3))
                self._grid[cell] = rounded
                self.map.points.append(rounded)
                added.append((cell, rounded))

        if len(self.map.points) > self.config.max_points:
            self.map.points = self.map.points[-self.config.max_points :]
            self._rebuild_grid()
        return added

    def _rebuild_grid(self):
        self._grid.clear()
        for point in self.map.points:
            self._grid[self._cell(point)] = point

    def _cell(self, point: XYPoint) -> tuple[int, int]:
        res = max(self.config.grid_resolution_m, 0.001)
        return (round(point[0] / res), round(point[1] / res))

    def _integrate_locked(self, snapshot: list[XYPoint], pose: Pose, name: str, result: MatchResult):
        previous_pose = Pose(self.map.pose.x, self.map.pose.y, self.map.pose.yaw)
        previous_initialized = self.map.initialized
        previous_updated_at = self.map.updated_at
        previous_debug_len = len(self.map.metadata.get("snapshots_debug", []))
        self.map.pose = pose
        added = self._merge_points(transform_points(snapshot, pose))
        self.map.initialized = True
        self.map.updated_at = time.time()
        debug = self.map.metadata.setdefault("snapshots_debug", [])
        debug.append({
            "name": name,
            "pose": pose.as_dict(),
            "points": len(snapshot),
            "match": result.as_dict(),
            "created_at": time.time(),
        })
        del debug[:-20]
        return {
            "added": added,
            "previous_pose": previous_pose,
            "previous_initialized": previous_initialized,
            "previous_updated_at": previous_updated_at,
            "previous_debug_len": previous_debug_len,
        }

    def _undo_last_integration_locked(self):
        integration = self._last_integration
        if integration is None:
            return
        added = integration.get("added", [])
        added_points = {point for _, point in added}
        added_cells = {cell for cell, _ in added}
        self.map.points = [point for point in self.map.points if point not in added_points]
        for cell in added_cells:
            self._grid.pop(cell, None)
        self.map.pose = integration["previous_pose"]
        self.map.initialized = integration["previous_initialized"]
        self.map.updated_at = integration["previous_updated_at"]
        debug = self.map.metadata.get("snapshots_debug", [])
        previous_debug_len = integration.get("previous_debug_len", len(debug))
        del debug[previous_debug_len:]
        self._last_integration = None
        self._rebuild_grid()

    def _candidates_with_preview(self, snapshot: list[XYPoint], candidates: list[dict]) -> list[dict]:
        enriched = []
        for candidate in candidates:
            item = dict(candidate)
            pose = Pose.from_dict(item.get("pose"))
            item["preview_points"] = [
                {"x": x, "y": y}
                for x, y in transform_points(snapshot, pose)[:2000]
            ]
            enriched.append(item)
        return enriched

    def _autosave(self):
        now = time.time()
        if now - self._last_save >= self.config.autosave_interval_s:
            self.save()
