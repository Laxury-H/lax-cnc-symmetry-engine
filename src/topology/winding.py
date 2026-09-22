"""
Winding Order Normalization and Toolpath Hierarchy Engine.
Standardizes loop orientation for CNC cutter radius compensation (G41 / G42):
  - Outer Boundary (Level 0): Normalized to Counter-Clockwise (CCW) [Climb Milling]
  - Interior Cavities / Holes (Level 1): Normalized to Clockwise (CW) [Opposite]
  - Islands inside Cavities (Level 2): CCW
Prevents tool path direction inversion after reflectional symmetry operations.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
from shapely.geometry import Polygon

from src.core.primitives import Point2D, LineSegment2D, Arc2D
from src.topology.cycle_finder import ClosedLoop


@dataclass
class NormalizedLoop:
    """A closed loop with established nesting level and standardized winding order."""
    loop_id: int
    points: List[Point2D]
    is_ccw: bool
    nesting_level: int           # 0 = outer boundary, 1 = cavity/hole, 2 = island, ...
    area: float
    is_outer_boundary: bool = False

    def to_lines(self, layer: str = "0") -> List[LineSegment2D]:
        """Converts normalized loop vertices to ordered LineSegment2D list."""
        lines = []
        n = len(self.points)
        for i in range(n):
            p1 = self.points[i]
            p2 = self.points[(i + 1) % n]
            if p1.distance_to(p2) > 1e-4:
                lines.append(LineSegment2D(start=p1, end=p2, layer=layer))
        return lines


def compute_signed_area(pts: List[Point2D]) -> float:
    """
    Computes signed area using Shoelace formula (Green's theorem).
    Area > 0 for Counter-Clockwise (CCW); Area < 0 for Clockwise (CW).
    """
    n = len(pts)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        area += (p1.x * p2.y - p2.x * p1.y)
    return area * 0.5


def reverse_loop(pts: List[Point2D]) -> List[Point2D]:
    """Reverses the vertex traversal order of a closed loop."""
    return pts[::-1]


class WindingNormalizer:
    """
    Analyzes spatial containment hierarchy and normalizes polygon winding order.
    """

    def __init__(self, outer_ccw: bool = True):
        self.outer_ccw = outer_ccw

    def is_ccw(self, loop: Any) -> bool:
        """Determines if a loop, NormalizedLoop, or Point2D list is counter-clockwise."""
        if hasattr(loop, "is_ccw"):
            return bool(loop.is_ccw)
        pts = loop.points if hasattr(loop, "points") else list(loop)
        return compute_signed_area(pts) > 0.0

    def normalize_loops(self, loops: List[Any]) -> List[NormalizedLoop]:
        """
        Takes raw loops (ClosedLoop or List[Point2D]), determines nesting depth via Shapely polygons,
        and standardizes winding direction according to nesting level.
        """
        if not loops:
            return []

        # 1. Build Shapely Polygons for each loop
        shapely_polys: List[Tuple[int, Polygon, List[Point2D], float]] = []
        for idx, loop in enumerate(loops):
            pts = loop.points if hasattr(loop, "points") else list(loop)
            if len(pts) < 3:
                continue
            poly_coords = [(p.x, p.y) for p in pts]
            if poly_coords[0] != poly_coords[-1]:
                poly_coords.append(poly_coords[0])
            try:
                poly = Polygon(poly_coords)
                if poly.is_valid and poly.area > 1e-4:
                    shapely_polys.append((idx, poly, pts, poly.area))
            except Exception:
                pass

        if not shapely_polys:
            return []

        # Sort by area descending
        shapely_polys.sort(key=lambda x: x[3], reverse=True)

        # 2. Determine nesting depth for each polygon
        normalized_results: List[NormalizedLoop] = []
        n_polys = len(shapely_polys)

        for i in range(n_polys):
            idx_i, poly_i, pts_i, area_i = shapely_polys[i]
            nesting_depth = 0

            # Count how many larger polygons contain poly_i
            for j in range(i):
                _, poly_j, _, _ = shapely_polys[j]
                if poly_j.contains(poly_i.centroid):
                    nesting_depth += 1

            # Determine target orientation:
            # Even depth (0, 2, 4...) -> outer_ccw
            # Odd depth (1, 3, 5...) -> opposite of outer_ccw
            target_is_ccw = self.outer_ccw if (nesting_depth % 2 == 0) else (not self.outer_ccw)

            current_area = compute_signed_area(pts_i)
            current_is_ccw = current_area > 0.0

            final_points = list(pts_i)
            if current_is_ccw != target_is_ccw:
                final_points = reverse_loop(final_points)

            normalized_results.append(NormalizedLoop(
                loop_id=idx_i,
                points=final_points,
                is_ccw=target_is_ccw,
                nesting_level=nesting_depth,
                area=abs(current_area),
                is_outer_boundary=(nesting_depth == 0)
            ))

        return normalized_results
