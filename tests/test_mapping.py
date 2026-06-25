import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
import numpy as np
from scipy.spatial import cKDTree

from mapping.map_model import Pose
from mapping.mapper import MapperConfig, PointCloudMapper, SnapshotCollector, SnapshotMatcher, polar_to_robot_xy, transform_points
from mapping.storage import MapStorage


def test_polar_to_robot_xy_convention():
    x, y = polar_to_robot_xy(270.0, 2.0)
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(0.0, abs=1e-6)

    x, y = polar_to_robot_xy(180.0, 2.0)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(-2.0)

    x, y = polar_to_robot_xy(360.0, 2.0)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(2.0)

    x, y = polar_to_robot_xy(180.0, 2.0, horizontal_flip=False)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(2.0)


def test_map_storage_and_waypoints(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("测试地图")
    point_map.add_waypoint("起点")
    storage.save(point_map)

    assert storage.list_maps() == ["测试地图"]
    loaded = storage.load("测试地图")
    assert "起点" in loaded.waypoints
    assert loaded.delete_waypoint("起点")
    assert "起点" not in loaded.waypoints


def test_mapper_initializes_first_scan(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    mapper = PointCloudMapper(point_map, storage, MapperConfig(min_snapshot_points=2))

    result = mapper.integrate_snapshot([(1.0, 0.0), (0.0, 1.0)], name="root")
    snapshot = mapper.snapshot()

    assert result.accepted
    assert snapshot["initialized"]
    assert len(snapshot["points"]) == 2
    assert snapshot["pose"] == {"x": 0.0, "y": 0.0, "yaw": 0.0}
    assert snapshot["last_snapshot_preview"] == [{"x": 1.0, "y": 0.0}, {"x": 0.0, "y": 1.0}]


def test_matcher_recovers_known_translation(tmp_path):
    config = MapperConfig(
        min_snapshot_points=6,
        global_yaw_step_deg=10.0,
        vote_resolution_m=0.1,
        trim_fraction=0.5,
        min_overlap_ratio=0.5,
        max_mean_error_m=0.2,
        ambiguity_score_gap=0.0,
    )
    local = [(0.0, 0.0), (0.4, 0.1), (0.9, -0.2), (1.1, 0.7), (0.2, 1.0), (-0.3, 0.4)]
    map_points = transform_points(local, Pose(0.5, -0.25, 30.0))
    result = SnapshotMatcher(config).match(local, map_points, Pose(0.0, 0.0, 0.0))

    assert result.accepted
    assert result.pose.x == pytest.approx(0.5, abs=0.15)
    assert result.pose.y == pytest.approx(-0.25, abs=0.15)
    assert result.pose.yaw == pytest.approx(30.0, abs=5.0)


def test_matcher_density_normalization_reduces_near_wall_bias():
    matcher = SnapshotMatcher(MapperConfig(match_density_resolution_m=0.2))
    dense_near_wall = np.array([(i * 0.01, 0.0) for i in range(100)], dtype=float)
    sparse_structure = np.array([(0.0, 1.0), (0.5, 1.2), (1.0, 1.0)], dtype=float)
    normalized = matcher._normalize_density(np.vstack([dense_near_wall, sparse_structure]))

    assert len(normalized) < 15
    assert any(np.allclose(point, (0.0, 1.0)) for point in normalized)


def test_matcher_rejects_single_wall_degenerate_alignment():
    config = MapperConfig(
        min_snapshot_points=20,
        global_yaw_step_deg=10.0,
        vote_resolution_m=0.1,
        trim_fraction=0.8,
        min_overlap_ratio=0.5,
        max_mean_error_m=0.05,
        min_inlier_short_axis_m=0.20,
        min_inlier_axis_ratio=0.08,
        ambiguity_score_gap=0.0,
    )
    wall = [(i * 0.1, 0.0) for i in range(60)]
    result = SnapshotMatcher(config).match(wall, wall, Pose())

    assert not result.accepted
    assert result.candidates[0]["geometry"]["accepted"] is False
    assert result.candidates[0]["geometry"]["short_axis_m"] < 0.20


def test_local_refine_improves_nearby_yaw_candidate():
    config = MapperConfig(
        min_snapshot_points=6,
        local_refine_yaw_deg=6.0,
        local_refine_yaw_step_deg=1.0,
        local_refine_xy_m=0.0,
        min_inlier_short_axis_m=0.01,
        min_inlier_axis_ratio=0.01,
    )
    matcher = SnapshotMatcher(config)
    source = matcher._to_array([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.2, 0.8), (-0.4, 0.7), (0.3, -0.5)])
    target = matcher._transform_array(source, Pose(0.0, 0.0, 4.0))
    tree = cKDTree(target)

    pose, overlap, error, geometry = matcher._local_refine(source, tree, Pose(0.0, 0.0, 0.0))

    assert pose.yaw == pytest.approx(4.0, abs=0.1)
    assert overlap == pytest.approx(1.0)
    assert error < 0.02


def test_failed_match_does_not_update_map(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig(min_snapshot_points=6, min_overlap_ratio=0.9, max_mean_error_m=0.01),
    )
    assert mapper.integrate_snapshot([(0.0, 0.0), (0.4, 0.1), (0.9, -0.2), (1.1, 0.7), (0.2, 1.0), (-0.3, 0.4)], name="root").accepted
    before = len(mapper.snapshot()["points"])

    result = mapper.integrate_snapshot([(0, 0), (2, 0), (4, 0), (6, 0), (8, 0), (10, 0)], name="bad")

    assert not result.accepted
    assert len(mapper.snapshot()["points"]) == before


def test_snapshot_preview_uses_map_coordinates(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    local = [(0.0, 0.0), (0.4, 0.1), (0.9, -0.2), (1.1, 0.7), (0.2, 1.0), (-0.3, 0.4)]
    expected = transform_points(local, Pose(2.0, 3.0, 0.0))
    point_map.points.extend(expected)
    point_map.initialized = True
    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig(
            min_snapshot_points=6,
            vote_resolution_m=0.1,
            min_overlap_ratio=0.75,
            max_mean_error_m=0.05,
            ambiguity_score_gap=0.0,
        ),
    )

    result = mapper.integrate_snapshot(local, initial_pose=Pose(2.0, 3.0, 0.0))
    snapshot = mapper.snapshot()

    assert result.accepted
    assert snapshot["last_snapshot_preview"] == [{"x": x, "y": y} for x, y in expected]


def test_ambiguous_match_waits_for_candidate_acceptance(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    point_map.points.extend(square)
    point_map.initialized = True
    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig(
            min_snapshot_points=4,
            vote_resolution_m=0.1,
            min_overlap_ratio=0.5,
            max_mean_error_m=0.05,
            ambiguity_score_gap=0.5,
        ),
    )

    result = mapper.integrate_snapshot(square, name="ambiguous")
    before = len(mapper.snapshot()["points"])

    assert not result.accepted
    assert result.ambiguous
    assert mapper.snapshot()["status"]["state"] == "ambiguous"
    accepted = mapper.accept_candidate(1, name="chosen")
    assert accepted.accepted
    assert len(mapper.snapshot()["points"]) == before


def test_discard_pending_snapshot_clears_candidates(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    point_map.points.extend(square)
    point_map.initialized = True
    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig(
            min_snapshot_points=4,
            vote_resolution_m=0.1,
            min_overlap_ratio=0.5,
            max_mean_error_m=0.05,
            ambiguity_score_gap=0.5,
        ),
    )
    assert mapper.integrate_snapshot(square, name="ambiguous").ambiguous

    snapshot = mapper.discard_pending_snapshot()

    assert snapshot["pending_candidates"] == []
    assert snapshot["last_snapshot_preview"] == []
    assert snapshot["status"]["state"] == "discarded"
    with pytest.raises(ValueError):
        mapper.accept_candidate(1)


def test_discard_undoes_first_integrated_snapshot(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    mapper = PointCloudMapper(point_map, storage, MapperConfig(min_snapshot_points=2))
    assert mapper.integrate_snapshot([(1.0, 0.0), (0.0, 1.0)], name="root").accepted

    snapshot = mapper.discard_pending_snapshot()

    assert not snapshot["initialized"]
    assert snapshot["points"] == []
    assert snapshot["last_snapshot_preview"] == []
    assert snapshot["status"]["state"] == "discarded"


def test_discard_undoes_latest_added_points_only(tmp_path):
    storage = MapStorage(tmp_path)
    point_map = storage.create("map")
    mapper = PointCloudMapper(
        point_map,
        storage,
        MapperConfig(min_snapshot_points=3, ambiguity_score_gap=0.0),
    )
    root = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    second = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (2.0, 2.0)]
    assert mapper.integrate_snapshot(root, name="root").accepted
    assert mapper.integrate_snapshot(second, name="second").accepted

    snapshot = mapper.discard_pending_snapshot()

    assert len(snapshot["points"]) == 3
    assert {"x": 2.0, "y": 2.0} not in snapshot["points"]


class _FakeLidar:
    def __init__(self):
        self.calls = 0
        self.flushes = 0

    def flush_input(self):
        self.flushes += 1

    def read_scan(self, timeout=0.3):
        self.calls += 1
        return [
            (0.0, 1.0, 200),
            (90.0, 1.0, 200),
            (180.0, 1.0, 200),
            (270.0, 1.0, 200),
        ]


def test_snapshot_collector_treats_0_to_360_as_full_circle():
    lidar = _FakeLidar()
    collector = SnapshotCollector(
        lidar,
        MapperConfig(
            angle_min=0.0,
            angle_max=360.0,
            snapshot_duration_s=0.01,
            snapshot_revolutions=5,
            robot_body_radius_m=0.3,
        ),
    )

    assert len(collector.collect()) == 4
    assert lidar.flushes == 1


class _DirtyLidar:
    def __init__(self):
        self.calls = 0

    def read_scan(self, timeout=0.3):
        self.calls += 1
        return [
            (270.0, 0.5, 200),
            (270.0, 0.7, 200),
            (180.0, 10.0, 200),
            (0.0, 10.1, 200),
        ]


def test_snapshot_collector_filters_near_and_far_points():
    collector = SnapshotCollector(
        _DirtyLidar(),
        MapperConfig(
            snapshot_duration_s=0.01,
            snapshot_revolutions=5,
            robot_body_radius_m=0.6,
            max_distance_m=10.0,
        ),
    )

    points = collector.collect()
    assert len(points) == 2
    assert any(point == pytest.approx((0.7, 0.0)) for point in points)
    assert any(point == pytest.approx((0.0, -10.0)) for point in points)


class _NoisyMultiScanLidar:
    def __init__(self):
        self.calls = 0

    def read_scan(self, timeout=0.3):
        self.calls += 1
        scan = [
            (270.0 + (self.calls % 2) * 0.4, 2.0 + 0.02 * self.calls, 200),
            (180.0, 3.0 + self.calls * 0.25, 200),
        ]
        if self.calls == 2:
            scan.append((90.0, 2.0, 200))
        return scan


def test_snapshot_collector_keeps_only_points_seen_in_all_revolutions_with_consistent_distance():
    collector = SnapshotCollector(
        _NoisyMultiScanLidar(),
        MapperConfig(
            snapshot_duration_s=0.01,
            snapshot_revolutions=5,
            snapshot_min_consensus_ratio=0.6,
            snapshot_consensus_angle_window_deg=1.0,
            snapshot_distance_tolerance_m=0.12,
            snapshot_distance_tolerance_ratio=0.05,
            robot_body_radius_m=0.6,
        ),
    )

    points = collector.collect()
    assert len(points) == 1
    assert points[0] == pytest.approx((2.06, 0.0))


class _SparseButStableLidar:
    def __init__(self):
        self.calls = 0

    def read_scan(self, timeout=0.3):
        self.calls += 1
        scan = []
        if self.calls in {1, 3, 5}:
            scan.append((270.0, 2.0 + self.calls * 0.01, 200))
        if self.calls == 2:
            scan.append((90.0, 2.0, 200))
        return scan


def test_snapshot_collector_keeps_points_seen_in_majority_revolutions():
    collector = SnapshotCollector(
        _SparseButStableLidar(),
        MapperConfig(
            snapshot_duration_s=0.01,
            snapshot_revolutions=5,
            snapshot_min_consensus_ratio=0.6,
            snapshot_distance_tolerance_m=0.12,
            robot_body_radius_m=0.6,
        ),
    )

    points = collector.collect()
    assert len(points) == 1
    assert points[0] == pytest.approx((2.03, 0.0))
