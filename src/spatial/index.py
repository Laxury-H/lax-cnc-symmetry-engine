"""
Spatial indexing for CAD/CAM entities using cKDTree and spatial grids.
Provides O(log N) nearest neighbor search and range queries.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Any, Dict
import numpy as np
from scipy.spatial import cKDTree

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D


class PointSpatialIndex:
    """Fast nearest-neighbor and radius search for 2D points via scipy.spatial.cKDTree."""

    def __init__(self, points: List[Point2D]):
        self.points = list(points)
        if self.points:
            self._coords = np.array([[p.x, p.y] for p in self.points], dtype=np.float64)
            self._tree = cKDTree(self._coords)
        else:
            self._coords = np.empty((0, 2), dtype=np.float64)
            self._tree = None

    def __len__(self) -> int:
        return len(self.points)

    def nearest(self, query_pt: Point2D) -> Tuple[Optional[Point2D], float, int]:
        """Find nearest point. Returns (nearest_point, distance, index) or (None, inf, -1)."""
        if self._tree is None or len(self.points) == 0:
            return (None, float("inf"), -1)
        dist, idx = self._tree.query([query_pt.x, query_pt.y], k=1)
        return (self.points[idx], float(dist), int(idx))

    def query_radius(self, query_pt: Point2D, radius: float) -> List[Tuple[Point2D, float, int]]:
        """Find all points within radius. Returns list of (point, distance, index)."""
        if self._tree is None or len(self.points) == 0:
            return []
        indices = self._tree.query_ball_point([query_pt.x, query_pt.y], r=radius)
        results = []
        for idx in indices:
            p = self.points[idx]
            d = query_pt.distance_to(p)
            results.append((p, d, int(idx)))
        results.sort(key=lambda x: x[1])
        return results

    def query_k_nearest(self, query_pt: Point2D, k: int) -> List[Tuple[Point2D, float, int]]:
        """Find k nearest points."""
        if self._tree is None or len(self.points) == 0:
            return []
        k = min(k, len(self.points))
        dists, indices = self._tree.query([query_pt.x, query_pt.y], k=k)
        if k == 1:
            dists = [dists]
            indices = [indices]
        return [(self.points[idx], float(d), int(idx)) for d, idx in zip(dists, indices)]


class SegmentSpatialIndex:
    """
    Spatial grid index for LineSegment2D objects.
    Enables efficient segment-segment distance queries and bounding-box intersection tests.
    """

    def __init__(self, segments: List[LineSegment2D], cell_size: float = 20.0):
        self.segments = list(segments)
        self.cell_size = max(1.0, cell_size)
        self._grid: Dict[Tuple[int, int], List[int]] = {}
        self._build_index()

    def _cell_coords(self, x: float, y: float) -> Tuple[int, int]:
        return (int(math_floor(x / self.cell_size)), int(math_floor(y / self.cell_size)))

    def _build_index(self):
        for idx, seg in enumerate(self.segments):
            bbox = seg.bbox
            min_c = self._cell_coords(bbox.min_x, bbox.min_y)
            max_c = self._cell_coords(bbox.max_x, bbox.max_y)
            for cx in range(min_c[0], max_c[0] + 1):
                for cy in range(min_c[1], max_c[1] + 1):
                    self._grid.setdefault((cx, cy), []).append(idx)

    def candidates_in_bbox(self, bbox: BoundingBox2D) -> List[LineSegment2D]:
        """Find segments whose bounding box cells intersect the query bbox."""
        min_c = self._cell_coords(bbox.min_x, bbox.min_y)
        max_c = self._cell_coords(bbox.max_x, bbox.max_y)
        seen = set()
        res = []
        for cx in range(min_c[0], max_c[0] + 1):
            for cy in range(min_c[1], max_c[1] + 1):
                for idx in self._grid.get((cx, cy), []):
                    if idx not in seen:
                        seen.add(idx)
                        seg = self.segments[idx]
                        if seg.bbox.intersects(bbox):
                            res.append(seg)
        return res

    def nearest_segment(self, pt: Point2D, max_search_radius: float = 100.0) -> Tuple[Optional[LineSegment2D], float]:
        """Find nearest segment to point within max_search_radius."""
        query_bbox = BoundingBox2D(
            pt.x - max_search_radius, pt.y - max_search_radius,
            pt.x + max_search_radius, pt.y + max_search_radius
        )
        candidates = self.candidates_in_bbox(query_bbox)
        if not candidates:
            # Fallback to brute force if outside local cells
            candidates = self.segments

        best_seg = None
        min_dist = float("inf")
        for seg in candidates:
            d = seg.distance_to_point(pt)
            if d < min_dist:
                min_dist = d
                best_seg = seg
        return (best_seg, min_dist)


def math_floor(val: float) -> int:
    import math
    return math.floor(val)
