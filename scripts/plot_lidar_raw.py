#!/usr/bin/env python3
"""Plot LD06 raw polar data — polar + Cartesian scatter, PNG to ~/Downloads."""
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

data_path = Path.home() / "Downloads" / "lidar_two_turns.json"
with open(data_path) as f:
    points = json.load(f)

angles_deg = [p["angle_deg"] for p in points]
distances_m = [p["distance_m"] for p in points]
confidences = [p["confidence"] for p in points]
angles_rad = [math.radians(a) for a in angles_deg]

fig = plt.figure(figsize=(16, 7))

# ── Left: polar scatter ──
ax_polar = fig.add_subplot(1, 2, 1, projection="polar")
sc = ax_polar.scatter(
    angles_rad, distances_m,
    c=confidences, cmap="viridis", s=3, alpha=0.8,
)
ax_polar.set_theta_zero_location("N")
ax_polar.set_theta_direction(-1)
ax_polar.set_title(
    f"LD06 Raw Data · Polar View\n"
    f"({len(points)} pts, 0deg=forward, clockwise)",
    fontsize=11,
)
cbar = plt.colorbar(sc, ax=ax_polar, label="Confidence (0-255)", shrink=0.7)

# ── Right: Cartesian XY ──
ax_xy = fig.add_subplot(1, 2, 2)
xs, ys = [], []
for a_deg, d_m in zip(angles_deg, distances_m):
    theta = math.radians(270.0 - a_deg)  # 270deg = robot forward → +X
    xs.append(d_m * math.cos(theta))
    ys.append(d_m * math.sin(theta))

ax_xy.scatter(xs, ys, c=confidences, cmap="viridis", s=3, alpha=0.8)
ax_xy.set_xlabel("X (m) forward")
ax_xy.set_ylabel("Y (m) left")
ax_xy.set_title("LD06 Raw Data · Cartesian View", fontsize=11)
ax_xy.set_aspect("equal")
ax_xy.grid(True, alpha=0.3)
ax_xy.scatter(0, 0, c="red", s=100, marker="o", zorder=5, label="Robot")
ax_xy.legend(fontsize=9)

fig.suptitle(
    f"LD06 LiDAR — 2 rotations raw data ({len(points)} pts, "
    f"range {min(distances_m):.2f}–{max(distances_m):.2f} m)",
    fontsize=13, y=1.02,
)
plt.tight_layout()

out_path = Path.home() / "Downloads" / "lidar_two_turns.png"
plt.savefig(out_path, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved: {out_path}")
print(f"Points: {len(points)}  |  Angle: {min(angles_deg):.1f}–{max(angles_deg):.1f} deg")
print(f"Distance: {min(distances_m):.3f}–{max(distances_m):.3f} m  |  Confidence: {min(confidences)}–{max(confidences)}")
