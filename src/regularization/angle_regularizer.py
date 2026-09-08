"""
Angle Regularizer.
Snaps near-canonical angles to exact mathematical orientations (0, 45, 90, 135 deg).
Supports both individual line segment snapping and vertex-preserving closed loop regularization.
"""

from __future__ import annotations
import math
from typing import List, Tuple

from src.core.primitives import Point2D, LineSegment2D, Vector2D


class AngleRegularizer:
    """
    Regularizes line and closed loop orientations to canonical angles without breaking loop closures.
    """

    def __init__(self, snap_tolerance_deg: float = 4.0):
        self.snap_tolerance_deg = snap_tolerance_deg

    def regularize_loop(self, pts: List[Point2D]) -> List[Point2D]:
        """
        Regularize edges of a closed loop to canonical angles by aligning vertex coordinates.
        Preserves 100% watertight loop closure (start and end vertices remain identical).
        """
        n = len(pts)
        if n < 3:
            return pts

        out = list(pts)
        for i in range(n):
            p1 = out[i]
            p2 = out[(i + 1) % n]
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            l = math.hypot(dx, dy)
            if l < 1e-4:
                continue

            ang = math.degrees(math.atan2(dy, dx)) % 180.0

            # Horizontal check
            if ang < self.snap_tolerance_deg or ang > (180.0 - self.snap_tolerance_deg):
                avg_y = (p1.y + p2.y) * 0.5
                out[i] = Point2D(p1.x, avg_y)
                out[(i + 1) % n] = Point2D(p2.x, avg_y)

            # Vertical check
            elif abs(ang - 90.0) < self.snap_tolerance_deg:
                avg_x = (p1.x + p2.x) * 0.5
                out[i] = Point2D(avg_x, p1.y)
                out[(i + 1) % n] = Point2D(avg_x, p2.y)

            # Diagonal 45 deg check (dx and dy should have same sign and equal length)
            elif abs(ang - 45.0) < self.snap_tolerance_deg:
                avg_span = (abs(dx) + abs(dy)) * 0.5
                sign_x = 1.0 if dx >= 0 else -1.0
                sign_y = 1.0 if dy >= 0 else -1.0
                mid_x = (p1.x + p2.x) * 0.5
                mid_y = (p1.y + p2.y) * 0.5
                half = avg_span * 0.5
                out[i] = Point2D(mid_x - sign_x * half, mid_y - sign_y * half)
                out[(i + 1) % n] = Point2D(mid_x + sign_x * half, mid_y + sign_y * half)

            # Diagonal 135 deg check (dx and dy have opposite signs)
            elif abs(ang - 135.0) < self.snap_tolerance_deg:
                avg_span = (abs(dx) + abs(dy)) * 0.5
                sign_x = 1.0 if dx >= 0 else -1.0
                sign_y = 1.0 if dy >= 0 else -1.0
                mid_x = (p1.x + p2.x) * 0.5
                mid_y = (p1.y + p2.y) * 0.5
                half = avg_span * 0.5
                out[i] = Point2D(mid_x - sign_x * half, mid_y - sign_y * half)
                out[(i + 1) % n] = Point2D(mid_x + sign_x * half, mid_y + sign_y * half)

        return out

    def regularize_lines(self, lines: List[LineSegment2D]) -> Tuple[List[LineSegment2D], int]:
        """
        Snap independent lines within snap_tolerance_deg of canonical angles (0, 45, 90, 135 deg)
        to their exact target orientation, rotating around their midpoint.
        """
        regularized: List[LineSegment2D] = []
        snapped_count = 0
        canonical_targets = [0.0, 45.0, 90.0, 135.0, 180.0]

        for line in lines:
            dx = line.end.x - line.start.x
            dy = line.end.y - line.start.y
            length = math.hypot(dx, dy)
            if length < 1e-4:
                continue

            ang = math.degrees(math.atan2(dy, dx)) % 180.0
            mid = Point2D((line.start.x + line.end.x) * 0.5, (line.start.y + line.end.y) * 0.5)

            best_target = None
            min_diff = float("inf")
            for t in canonical_targets:
                diff = abs(ang - t)
                if diff < min_diff:
                    min_diff = diff
                    best_target = 0.0 if t == 180.0 else t

            if min_diff <= self.snap_tolerance_deg and best_target is not None and min_diff > 1e-3:
                rad = math.radians(best_target)
                half_len = length * 0.5
                dir_vec = Vector2D(math.cos(rad) * half_len, math.sin(rad) * half_len)
                new_start = mid - dir_vec
                new_end = mid + dir_vec
                regularized.append(LineSegment2D(start=new_start, end=new_end, layer=line.layer))
                snapped_count += 1
            else:
                regularized.append(line)

        return regularized, snapped_count
