"""
Spatial Density Clustering for Local vs. Global Symmetry Analysis.
Separates independent decorative motifs, cutouts, and asymmetric outer frames
(e.g., gates with offset lock holes or beveled panels) using spatial clustering.
Enables local symmetry detection and repair without distortion from asymmetric boundaries.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional, Union
import numpy as np
from scipy.spatial import cKDTree

from src.core.primitives import Point2D, LineSegment2D, Arc2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.io.dxf_io import CADModel2D
from src.topology.cycle_finder import ClosedLoop


@dataclass
class MotifCluster:
    """A distinct spatial cluster of connected or adjacent geometric elements."""
    cluster_id: int
    primitives: List[Union[LineSegment2D, Arc2D]] = field(default_factory=list)
    bbox: BoundingBox2D = field(default_factory=lambda: BoundingBox2D(0, 0, 0, 0))
    centroid: Point2D = field(default_factory=lambda: Point2D(0, 0))
    is_outer_frame: bool = False
    local_axis: Optional[SymmetryAxis2D] = None
    local_symmetry_score: float = 0.0

    def sample_points(self, num_points_per_entity: int = 8) -> List[Point2D]:
        pts = []
        for prim in self.primitives:
            if isinstance(prim, LineSegment2D):
                pts.extend(prim.sample_points(num_points_per_entity))
            elif isinstance(prim, Arc2D):
                pts.extend(arc_samples(prim, num_points_per_entity))
        return pts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "primitives_count": len(self.primitives),
            "is_outer_frame": self.is_outer_frame,
            "bbox": {
                "min_x": round(self.bbox.min_x, 2), "max_x": round(self.bbox.max_x, 2),
                "min_y": round(self.bbox.min_y, 2), "max_y": round(self.bbox.max_y, 2),
                "width": round(self.bbox.width, 2), "height": round(self.bbox.height, 2)
            },
            "centroid": self.centroid.to_dict(),
            "local_symmetry_score": round(self.local_symmetry_score, 2),
            "local_axis_angle": round(self.local_axis.angle_degrees, 2) if self.local_axis else None
        }


def arc_samples(arc: Arc2D, n: int = 8) -> List[Point2D]:
    pts = []
    sweep = arc.sweep_angle
    sign = 1.0 if arc.is_ccw else -1.0
    for i in range(n):
        t = i / max(1, n - 1)
        ang = arc.start_angle + sign * t * sweep
        pts.append(Point2D(
            arc.center.x + arc.radius * math.cos(ang),
            arc.center.y + arc.radius * math.sin(ang)
        ))
    return pts


class SpatialMotifClusterer:
    """
    Groups geometric primitives into discrete clusters by spatial proximity.
    """

    def __init__(self, cluster_distance_mm: float = 30.0):
        self.cluster_distance = cluster_distance_mm

    def cluster_model(
        self,
        model: CADModel2D,
        loops: Optional[List[ClosedLoop]] = None
    ) -> List[MotifCluster]:
        """
        Partitions the CAD model entities into distinct motif clusters.
        """
        all_prims: List[Union[LineSegment2D, Arc2D]] = list(model.lines) + list(model.arcs)
        if not all_prims:
            return []

        # 1. Identify outer frame if loops are provided
        outer_bbox = model.bbox
        outer_prims = set()
        if loops and len(loops) > 1:
            largest_loop = max(loops, key=lambda l: l.area)
            # Match primitives in largest loop
            outer_points = set(p.quantize(0.1) for p in largest_loop.points)
            for prim in all_prims:
                p_start = prim.start if isinstance(prim, LineSegment2D) else prim.start_point
                p_end = prim.end if isinstance(prim, LineSegment2D) else prim.end_point
                if p_start.quantize(0.1) in outer_points and p_end.quantize(0.1) in outer_points:
                    outer_prims.add(id(prim))

        # 2. Extract representative centers for each primitive
        centers = []
        interior_prims = []
        outer_list = []

        for prim in all_prims:
            if id(prim) in outer_prims:
                outer_list.append(prim)
            else:
                interior_prims.append(prim)
                c = prim.midpoint
                centers.append([c.x, c.y])

        clusters: List[MotifCluster] = []

        # Add outer frame cluster if exists
        if outer_list:
            all_pts = []
            for p in outer_list:
                if isinstance(p, LineSegment2D):
                    all_pts.extend([p.start, p.end])
                else:
                    all_pts.extend([p.start_point, p.end_point])
            b = BoundingBox2D.from_points(all_pts)
            clusters.append(MotifCluster(
                cluster_id=0,
                primitives=outer_list,
                bbox=b,
                centroid=b.center,
                is_outer_frame=True
            ))

        if not interior_prims:
            return clusters

        # 3. Graph connected components on proximity graph via KD-Tree
        tree = cKDTree(np.array(centers))
        n_prims = len(interior_prims)
        visited = set()
        cluster_counter = 1

        for i in range(n_prims):
            if i in visited:
                continue

            # BFS expansion for connected cluster
            current_cluster_indices = []
            queue = [i]
            visited.add(i)

            while queue:
                idx = queue.pop(0)
                current_cluster_indices.append(idx)
                # Find neighbors within cluster_distance
                neighbors = tree.query_ball_point(centers[idx], r=self.cluster_distance)
                for nb in neighbors:
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)

            c_prims = [interior_prims[idx] for idx in current_cluster_indices]
            all_pts = []
            for p in c_prims:
                if isinstance(p, LineSegment2D):
                    all_pts.extend([p.start, p.end])
                else:
                    all_pts.extend([p.start_point, p.end_point])
            b = BoundingBox2D.from_points(all_pts)

            clusters.append(MotifCluster(
                cluster_id=cluster_counter,
                primitives=c_prims,
                bbox=b,
                centroid=b.center,
                is_outer_frame=False
            ))
            cluster_counter += 1

        # 4. Compute local symmetry for each interior cluster
        from src.symmetry.axis_finder import SymmetryAxisFinder
        axis_finder = SymmetryAxisFinder(tolerance=0.25)

        for cl in clusters:
            if not cl.is_outer_frame and len(cl.primitives) >= 4:
                cl_pts = cl.sample_points(6)
                if len(cl_pts) >= 8:
                    try:
                        best_ax, best_prof = axis_finder.find_best_axis(cl_pts)
                        cl.local_axis = best_ax
                        cl.local_symmetry_score = best_prof.symmetry_score
                    except Exception:
                        pass

        return clusters
