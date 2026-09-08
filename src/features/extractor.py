"""
Geometric feature extraction from CAD models and topological graphs.
Converts raw lines/arcs into semantic geometric features with rich structural metadata.
"""

from __future__ import annotations
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional, Set, Any
import numpy as np

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph, TopologyNode, TopologyEdge
from src.topology.cycle_finder import CycleFinder, ClosedLoop


class OrientationClass(Enum):
    HORIZONTAL = "HORIZONTAL"       # Near 0 deg or 180 deg
    VERTICAL = "VERTICAL"           # Near 90 deg
    DIAGONAL_45 = "DIAGONAL_45"     # Near 45 deg
    DIAGONAL_135 = "DIAGONAL_135"   # Near 135 deg
    OBLIQUE = "OBLIQUE"             # Other freeform / arbitrary angles


@dataclass
class GeometricFeature:
    """Base class for geometric features."""
    feature_id: str
    feature_type: str
    bbox: BoundingBox2D
    layer: str = "0"
    importance: str = "STANDARD"  # FIXED, STRUCTURAL, STANDARD, DECORATIVE


@dataclass
class LineFeature(GeometricFeature):
    """Line segment feature with orientation and canonical alignment metadata."""
    start: Point2D = field(default_factory=lambda: Point2D(0, 0))
    end: Point2D = field(default_factory=lambda: Point2D(0, 0))
    length: float = 0.0
    angle_deg: float = 0.0          # [0, 180) degrees
    orientation: OrientationClass = OrientationClass.OBLIQUE
    canonical_angle_deg: float = 0.0
    angle_deviation_deg: float = 0.0  # Deviation from nearest canonical angle (0, 45, 90, 135)
    midpoint: Point2D = field(default_factory=lambda: Point2D(0, 0))
    connected_node_ids: Tuple[int, int] = (-1, -1)

    @classmethod
    def from_line(cls, line: LineSegment2D, fid: str = "", tol_angle: float = 4.0) -> LineFeature:
        dx = line.end.x - line.start.x
        dy = line.end.y - line.start.y
        length = math.hypot(dx, dy)
        ang = math.degrees(math.atan2(dy, dx)) % 180.0
        mid = Point2D((line.start.x + line.end.x) * 0.5, (line.start.y + line.end.y) * 0.5)

        # Classify orientation
        orient, canon_ang, dev = cls._classify_angle(ang, tol_angle)

        return cls(
            feature_id=fid,
            feature_type="LINE",
            bbox=line.bbox,
            layer=line.layer,
            start=line.start,
            end=line.end,
            length=length,
            angle_deg=ang,
            orientation=orient,
            canonical_angle_deg=canon_ang,
            angle_deviation_deg=dev,
            midpoint=mid
        )

    @staticmethod
    def _classify_angle(ang: float, tol: float = 4.0) -> Tuple[OrientationClass, float, float]:
        targets = [(0.0, OrientationClass.HORIZONTAL),
                   (45.0, OrientationClass.DIAGONAL_45),
                   (90.0, OrientationClass.VERTICAL),
                   (135.0, OrientationClass.DIAGONAL_135),
                   (180.0, OrientationClass.HORIZONTAL)]

        best_canon = 0.0
        best_orient = OrientationClass.OBLIQUE
        min_diff = float("inf")

        for target_ang, orient_class in targets:
            diff = abs(ang - target_ang)
            if diff < min_diff:
                min_diff = diff
                best_canon = 0.0 if target_ang == 180.0 else target_ang
                best_orient = orient_class

        if min_diff <= tol:
            return best_orient, best_canon, min_diff
        return OrientationClass.OBLIQUE, ang, 0.0


@dataclass
class ArcFeature(GeometricFeature):
    """Arc entity feature."""
    center: Point2D = field(default_factory=lambda: Point2D(0, 0))
    radius: float = 0.0
    start_angle_deg: float = 0.0
    end_angle_deg: float = 0.0
    span_deg: float = 0.0
    arc_length: float = 0.0


@dataclass
class CornerFeature(GeometricFeature):
    """Corner vertex where 2 line features intersect."""
    vertex: Point2D = field(default_factory=lambda: Point2D(0, 0))
    edge_ids: Tuple[str, str] = ("", "")
    corner_angle_deg: float = 90.0
    is_orthogonal: bool = True       # Near 90 degrees
    bisector: Vector2D = field(default_factory=lambda: Vector2D(0, 0))


@dataclass
class JunctionFeature(GeometricFeature):
    """Junction where 3 or more entities connect."""
    vertex: Point2D = field(default_factory=lambda: Point2D(0, 0))
    degree: int = 3
    connected_feature_ids: List[str] = field(default_factory=list)


@dataclass
class LoopFeature(GeometricFeature):
    """Closed loop motif feature."""
    centroid: Point2D = field(default_factory=lambda: Point2D(0, 0))
    area: float = 0.0
    perimeter: float = 0.0
    vertex_count: int = 0
    width: float = 0.0
    height: float = 0.0
    aspect_ratio: float = 1.0
    loop_category: str = "DECORATIVE"  # OUTER_BOUNDARY, CENTER_BOX, CORNER_BOX, AXIS_BAR, BRACE_CONNECTOR
    points: List[Point2D] = field(default_factory=list)
    edge_feature_ids: List[str] = field(default_factory=list)


class FeatureExtractor:
    """
    Extracts semantic geometric features from CADModel2D and TopologyGraph.
    """

    def __init__(self, angle_tolerance: float = 4.0, endpoint_tolerance: float = 0.10):
        self.angle_tolerance = angle_tolerance
        self.endpoint_tolerance = endpoint_tolerance

    def extract(self, model: CADModel2D, graph: Optional[TopologyGraph] = None) -> Dict[str, Any]:
        """Extract all features from model."""
        if graph is None:
            graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=self.endpoint_tolerance)

        lines: List[LineFeature] = []
        for i, l in enumerate(model.lines):
            lf = LineFeature.from_line(l, fid=f"line_{i}", tol_angle=self.angle_tolerance)
            lines.append(lf)

        arcs: List[ArcFeature] = []
        for i, a in enumerate(model.arcs):
            span = a.sweep_angle_deg
            length = (span / 360.0) * (2.0 * math.pi * a.radius)
            arcs.append(ArcFeature(
                feature_id=f"arc_{i}",
                feature_type="ARC",
                bbox=a.bbox,
                layer=a.layer,
                center=a.center,
                radius=a.radius,
                start_angle_deg=math.degrees(a.start_angle),
                end_angle_deg=math.degrees(a.end_angle),
                span_deg=span,
                arc_length=length
            ))

        # Extract corners & junctions from topology graph nodes
        corners: List[CornerFeature] = []
        junctions: List[JunctionFeature] = []

        for node_id, node in graph.nodes.items():
            deg = node.degree
            if deg == 2:
                # Corner candidate
                connected_edges = [graph.edges[eid] for eid in node.connected_edge_ids if eid in graph.edges]
                if len(connected_edges) == 2 and isinstance(connected_edges[0].geometry, LineSegment2D) and isinstance(connected_edges[1].geometry, LineSegment2D):
                    l1, l2 = connected_edges[0].geometry, connected_edges[1].geometry
                    p1_other = l1.end if l1.start.distance_to(node.point) < l1.end.distance_to(node.point) else l1.start
                    p2_other = l2.end if l2.start.distance_to(node.point) < l2.end.distance_to(node.point) else l2.start
                    v1 = (p1_other - node.point).normalized()
                    v2 = (p2_other - node.point).normalized()
                    ang_rad = v1.angle_with(v2)
                    ang_deg = math.degrees(ang_rad)
                    is_ortho = abs(ang_deg - 90.0) <= self.angle_tolerance
                    bisector = (v1 + v2).normalized() if (v1 + v2).length > 1e-6 else Vector2D(0, 0)
                    corners.append(CornerFeature(
                        feature_id=f"corner_{node_id}",
                        feature_type="CORNER",
                        bbox=BoundingBox2D(node.point.x, node.point.x, node.point.y, node.point.y),
                        vertex=node.point,
                        edge_ids=(f"edge_{connected_edges[0].edge_id}", f"edge_{connected_edges[1].edge_id}"),
                        corner_angle_deg=ang_deg,
                        is_orthogonal=is_ortho,
                        bisector=bisector
                    ))
            elif deg >= 3:
                junctions.append(JunctionFeature(
                    feature_id=f"junction_{node_id}",
                    feature_type="JUNCTION",
                    bbox=BoundingBox2D(node.point.x, node.point.x, node.point.y, node.point.y),
                    vertex=node.point,
                    degree=deg,
                    connected_feature_ids=[f"edge_{eid}" for eid in node.connected_edge_ids]
                ))

        # Extract loops and classify them
        cycle_finder = CycleFinder(graph)
        all_loops = cycle_finder.extract_loops()
        bbox = model.bbox
        cx, cy = (bbox.min_x + bbox.max_x) * 0.5, (bbox.min_y + bbox.max_y) * 0.5

        loop_features: List[LoopFeature] = []
        for i, loop in enumerate(all_loops):
            c = loop.centroid
            xs = [p.x for p in loop.points]
            ys = [p.y for p in loop.points]
            w = max(xs) - min(xs) if xs else 0.0
            h = max(ys) - min(ys) if ys else 0.0
            ar = w / h if h > 1e-6 else 1.0

            # Classify category
            if i == 0:
                cat = "OUTER_BOUNDARY"
                imp = "FIXED"
            elif abs(c.x - cx) < bbox.width * 0.08 and abs(c.y - cy) < bbox.height * 0.08:
                cat = "CENTER_BOX"
                imp = "STRUCTURAL"
            elif abs(c.x - cx) > bbox.width * 0.25 and abs(c.y - cy) > bbox.height * 0.25 and len(loop.points) == 4:
                cat = "CORNER_BOX"
                imp = "STRUCTURAL"
            elif (abs(c.x - cx) < bbox.width * 0.08 or abs(c.y - cy) < bbox.height * 0.08) and len(loop.points) >= 4:
                cat = "AXIS_BAR"
                imp = "STRUCTURAL"
            else:
                cat = "BRACE_CONNECTOR"
                imp = "STANDARD"

            loop_features.append(LoopFeature(
                feature_id=f"loop_{i}",
                feature_type="LOOP",
                bbox=BoundingBox2D(min(xs), max(xs), min(ys), max(ys)),
                importance=imp,
                centroid=c,
                area=abs(loop.area),
                perimeter=sum(loop.points[j].distance_to(loop.points[(j + 1) % len(loop.points)]) for j in range(len(loop.points))),
                vertex_count=len(loop.points),
                width=w,
                height=h,
                aspect_ratio=ar,
                loop_category=cat,
                points=loop.points
            ))

        return {
            "lines": lines,
            "arcs": arcs,
            "corners": corners,
            "junctions": junctions,
            "loops": loop_features,
            "outer_loop": loop_features[0] if loop_features else None,
            "panel_bbox": bbox
        }
