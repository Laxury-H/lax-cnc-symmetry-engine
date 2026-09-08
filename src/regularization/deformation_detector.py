"""
Deformation and Kink ("Móp méo") Detector.
Identifies subtle geometric defects:
  - Broken collinear lines forming kinked angles (174 - 179.5 deg)
  - Micro-segments causing fractured junctions (< 1.5 mm)
  - Distorted or sheared rectangular motifs
  - Pinch / flare channel variations
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any

from src.core.primitives import Point2D, LineSegment2D, Vector2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder, ClosedLoop


@dataclass
class KinkDefect:
    """A junction where two edges form an unintended bent/kink angle."""
    vertex: Point2D
    angle_deg: float         # e.g. 177.5 deg
    kink_deviation_deg: float # e.g. 2.5 deg from straight 180 deg
    description: str = ""


@dataclass
class DeformationReport:
    """Comprehensive analysis of geometric deformation and kinks."""
    kinks: List[KinkDefect]
    micro_segments_count: int
    skewed_corners_count: int
    deformation_score: float   # 0.0 (perfectly smooth) to 100.0 (heavily warped)
    is_acceptable: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_kinks": len(self.kinks),
            "worst_kink_dev_deg": round(max((k.kink_deviation_deg for k in self.kinks), default=0.0), 2),
            "micro_segments_count": self.micro_segments_count,
            "skewed_corners_count": self.skewed_corners_count,
            "deformation_score": round(self.deformation_score, 2),
            "is_acceptable": self.is_acceptable
        }


class DeformationDetector:
    """
    Detects kinks, micro-segment buckling, and skew in CAD models.
    """

    def __init__(self, kink_threshold_deg: float = 6.0, micro_length_mm: float = 1.5):
        self.kink_threshold_deg = kink_threshold_deg
        self.micro_length_mm = micro_length_mm

    def analyze(self, model: CADModel2D, graph: Optional[TopologyGraph] = None) -> DeformationReport:
        if graph is None:
            graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=0.10)

        kinks: List[KinkDefect] = []
        micro_count = 0

        # 1. Check for micro-segments
        for line in model.lines:
            if line.length < self.micro_length_mm:
                micro_count += 1

        # 2. Check for kinked degree-2 nodes
        for node_id, node in graph.nodes.items():
            if node.degree == 2:
                connected = [graph.edges[eid] for eid in node.connected_edge_ids if eid in graph.edges]
                if len(connected) == 2 and isinstance(connected[0].geometry, LineSegment2D) and isinstance(connected[1].geometry, LineSegment2D):
                    l1, l2 = connected[0].geometry, connected[1].geometry
                    p1_other = l1.end if l1.start.distance_to(node.point) < l1.end.distance_to(node.point) else l1.start
                    p2_other = l2.end if l2.start.distance_to(node.point) < l2.end.distance_to(node.point) else l2.start

                    v1 = (p1_other - node.point).normalized()
                    v2 = (p2_other - node.point).normalized()

                    if v1.length > 1e-6 and v2.length > 1e-6:
                        ang_deg = math.degrees(v1.angle_with(v2))
                        # If angle is between 174 deg and 179.5 deg, it's an unintended kink in a straight line
                        if 180.0 - self.kink_threshold_deg <= ang_deg <= 179.7:
                            dev = 180.0 - ang_deg
                            kinks.append(KinkDefect(
                                vertex=node.point,
                                angle_deg=ang_deg,
                                kink_deviation_deg=dev,
                                description=f"Kinked junction: angle={ang_deg:.1f} deg (bent by {dev:.1f} deg)"
                            ))

        # 3. Check for skewed 4-vertex loops (should be orthogonal rectangles)
        cycle_finder = CycleFinder(graph)
        loops = cycle_finder.extract_loops()
        skewed_count = 0

        for loop in loops:
            if len(loop.points) == 4:
                pts = loop.points
                # Check angles at 4 vertices
                angles = []
                for i in range(4):
                    p_prev = pts[(i - 1) % 4]
                    p_curr = pts[i]
                    p_next = pts[(i + 1) % 4]
                    v_in = (p_prev - p_curr).normalized()
                    v_out = (p_next - p_curr).normalized()
                    ang = math.degrees(v_in.angle_with(v_out))
                    angles.append(ang)

                # If any angle is not ~90 deg (e.g. sheared parallelogram/trapezoid)
                for a in angles:
                    if abs(a - 90.0) > 2.5:
                        skewed_count += 1
                        break

        # Calculate composite deformation score (0.0 = perfect, 100.0 = ruined)
        kink_penalty = min(50.0, sum(k.kink_deviation_deg * 4.0 for k in kinks))
        micro_penalty = min(25.0, micro_count * 5.0)
        skew_penalty = min(25.0, skewed_count * 4.0)

        total_score = kink_penalty + micro_penalty + skew_penalty

        return DeformationReport(
            kinks=kinks,
            micro_segments_count=micro_count,
            skewed_corners_count=skewed_count,
            deformation_score=total_score,
            is_acceptable=(total_score < 12.0)
        )
