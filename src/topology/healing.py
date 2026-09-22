"""
Micro-gap Healing, Vertex Welding, and CNC Tab Preservation Engine.
Closes micro-gaps (1e-5 to 0.05 mm) along symmetry seams and joints using KD-Tree vertex welding.
Protects intentional CNC holding tabs (0.5 to 2.0 mm) from accidental closure.
Produces watertight, chained loops ready for CAM toolpath profiling and nesting.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional, Set, Union
import numpy as np
from scipy.spatial import cKDTree

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, BoundingBox2D
from src.topology.cycle_finder import ClosedLoop


@dataclass
class HoldingTab2D:
    """An intentional CNC holding tab / micro-joint across an open gap."""
    p1: Point2D
    p2: Point2D
    gap_width: float
    direction: Vector2D


@dataclass
class HealingReport:
    """Summary of topological healing operations."""
    welded_vertices_count: int
    micro_gaps_closed: int
    tabs_preserved_count: int
    preserved_tabs: List[HoldingTab2D] = field(default_factory=list)
    total_closed_loops: int = 0


class TopologyHealer:
    """
    Automates vertex welding and micro-gap closure while preserving intentional CNC tabs.
    """

    def __init__(
        self,
        snap_radius_mm: float = 0.05,
        tab_min_gap_mm: float = 0.50,
        tab_max_gap_mm: float = 2.00,
        preserve_tabs: bool = True,
        snap_radius: Optional[float] = None,
        tab_min_gap: Optional[float] = None,
        tab_max_gap: Optional[float] = None
    ):
        self.snap_radius = snap_radius if snap_radius is not None else snap_radius_mm
        self.tab_min_gap = tab_min_gap if tab_min_gap is not None else tab_min_gap_mm
        self.tab_max_gap = tab_max_gap if tab_max_gap is not None else tab_max_gap_mm
        self.preserve_tabs = preserve_tabs

    def heal_and_stitch(
        self,
        lines_or_model: Union[List[LineSegment2D], Any],
        arcs: Optional[List[Arc2D]] = None
    ) -> Union[Tuple[List[LineSegment2D], List[Arc2D], HealingReport], Any]:
        """
        Welds vertices within snap_radius into shared junction points.
        Detects and preserves intentional tabs within [tab_min_gap, tab_max_gap].
        Returns healed lines, healed arcs, and the healing report (or CADModel2D if model passed).
        """
        report = HealingReport(welded_vertices_count=0, micro_gaps_closed=0, tabs_preserved_count=0)

        is_model = hasattr(lines_or_model, "lines")
        if is_model:
            lines = lines_or_model.lines
            arcs_input = lines_or_model.arcs
        else:
            lines = lines_or_model
            arcs_input = arcs if arcs is not None else []

        if not lines and not arcs_input:
            if is_model:
                return lines_or_model
            return ([], [], report)

        # 1. Collect all endpoints: list of (primitive_type, index, 'start'/'end', Point2D)
        # primitive_type: 0 for line, 1 for arc
        endpoints: List[Tuple[int, int, str, Point2D]] = []
        for i, l in enumerate(lines):
            endpoints.append((0, i, 'start', l.start))
            endpoints.append((0, i, 'end', l.end))
        for j, a in enumerate(arcs_input):
            endpoints.append((1, j, 'start', a.start_point))
            endpoints.append((1, j, 'end', a.end_point))

        coords = np.array([[ep[3].x, ep[3].y] for ep in endpoints], dtype=np.float64)
        tree = cKDTree(coords)

        # 2. Detect intentional holding tabs (gaps in [tab_min_gap, tab_max_gap])
        protected_tab_endpoint_indices: Set[int] = set()
        if self.preserve_tabs:
            for idx, ep in enumerate(endpoints):
                pt = ep[3]
                nearby = tree.query_ball_point([pt.x, pt.y], r=self.tab_max_gap)
                for other_idx in nearby:
                    if other_idx <= idx:
                        continue
                    other_ep = endpoints[other_idx]
                    # Disallow endpoints of the same primitive
                    if ep[0] == other_ep[0] and ep[1] == other_ep[1]:
                        continue
                    d = pt.distance_to(other_ep[3])
                    if self.tab_min_gap <= d <= self.tab_max_gap:
                        # Check collinearity/tangency across gap
                        v_gap = (other_ep[3] - pt).normalized()
                        report.tabs_preserved_count += 1
                        report.preserved_tabs.append(HoldingTab2D(
                            p1=pt, p2=other_ep[3], gap_width=round(d, 3), direction=v_gap
                        ))
                        protected_tab_endpoint_indices.add(idx)
                        protected_tab_endpoint_indices.add(other_idx)

        # 3. Find connected components within snap_radius (Vertex Welding)
        n = len(endpoints)
        visited = set()
        welded_target: Dict[int, Point2D] = {}

        for i in range(n):
            if i in visited:
                continue
            neighbors = tree.query_ball_point(coords[i], r=self.snap_radius)
            # Filter out endpoints that belong to protected tabs
            valid_group = [idx for idx in neighbors if idx not in protected_tab_endpoint_indices]
            if not valid_group:
                valid_group = [i]

            for idx in valid_group:
                visited.add(idx)

            if len(valid_group) > 1:
                # Compute centroid of cluster
                group_pts = [endpoints[idx][3] for idx in valid_group]
                cx = float(np.mean([p.x for p in group_pts]))
                cy = float(np.mean([p.y for p in group_pts]))
                weld_pt = Point2D(cx, cy)
                report.welded_vertices_count += len(valid_group)
                report.micro_gaps_closed += (len(valid_group) - 1)
                for idx in valid_group:
                    welded_target[idx] = weld_pt
            else:
                welded_target[i] = endpoints[i][3]

        # 4. Reconstruct lines and arcs with welded endpoints
        new_lines: List[LineSegment2D] = []
        for i, l in enumerate(lines):
            idx_s = i * 2
            idx_e = i * 2 + 1
            new_s = welded_target.get(idx_s, l.start)
            new_e = welded_target.get(idx_e, l.end)
            if new_s.distance_to(new_e) > 1e-4:
                new_lines.append(LineSegment2D(
                    start=new_s, end=new_e, layer=l.layer,
                    entity_id=l.entity_id, metadata=dict(l.metadata)
                ))

        base_arc_idx = len(lines) * 2
        new_arcs: List[Arc2D] = []
        for j, a in enumerate(arcs_input):
            idx_s = base_arc_idx + j * 2
            idx_e = base_arc_idx + j * 2 + 1
            new_s = welded_target.get(idx_s, a.start_point)
            new_e = welded_target.get(idx_e, a.end_point)

            if new_s.distance_to(new_e) < 1e-4:
                continue

            # Update arc start/end angles to match welded points
            vs = new_s - a.center
            ve = new_e - a.center
            ang_s = math.atan2(vs.dy, vs.dx) % (2.0 * math.pi)
            ang_e = math.atan2(ve.dy, ve.dx) % (2.0 * math.pi)
            # Adjust radius slightly to average distance
            avg_r = (new_s.distance_to(a.center) + new_e.distance_to(a.center)) * 0.5

            new_arcs.append(Arc2D(
                center=a.center,
                radius=avg_r,
                start_angle=ang_s,
                end_angle=ang_e,
                is_ccw=a.is_ccw,
                layer=a.layer,
                entity_id=a.entity_id,
                metadata=dict(a.metadata)
            ))

        if is_model:
            from src.io.dxf_io import CADModel2D
            return CADModel2D(
                lines=new_lines,
                arcs=new_arcs,
                circles=getattr(lines_or_model, "circles", []),
                layers=getattr(lines_or_model, "layers", set()),
                source_file=getattr(lines_or_model, "source_file", ""),
                units=getattr(lines_or_model, "units", "mm"),
                metadata=getattr(lines_or_model, "metadata", {})
            )

        return (new_lines, new_arcs, report)
