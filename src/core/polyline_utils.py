"""
Polyline and Bulge Normalization Engine for DXF LWPOLYLINE Entities.
Handles exact conversion between bulge-encoded polylines and LineSegment2D / Arc2D primitives.
Mathematically guarantees correct bulge sign inversion and chirality mapping
under reflection matrices and vertex reordering so arcs never flip from convex to concave.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Tuple, Optional, Union, Dict, Any

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D
from src.core.transform import SymmetryAxis2D


@dataclass
class PolylineVertex2D:
    """A 2D vertex with an associated DXF bulge parameter."""
    x: float
    y: float
    bulge: float = 0.0

    @property
    def point(self) -> Point2D:
        return Point2D(self.x, self.y)

    def to_tuple(self) -> Tuple[float, float, float]:
        return (self.x, self.y, self.bulge)


def arc_to_bulge(start: Point2D, end: Point2D, center: Point2D, is_ccw: bool) -> float:
    """
    Computes standard DXF bulge = tan(theta / 4) for an arc from start to end.
    Bulge > 0 for CCW arcs, < 0 for CW arcs.
    """
    chord = start.distance_to(end)
    if chord < 1e-9:
        return 0.0

    v_start = start - center
    v_end = end - center
    ang1 = math.atan2(v_start.dy, v_start.dx) % (2.0 * math.pi)
    ang2 = math.atan2(v_end.dy, v_end.dx) % (2.0 * math.pi)

    if is_ccw:
        theta = (ang2 - ang1) % (2.0 * math.pi)
        if theta == 0.0:
            theta = 2.0 * math.pi
        sign = 1.0
    else:
        theta = (ang1 - ang2) % (2.0 * math.pi)
        if theta == 0.0:
            theta = 2.0 * math.pi
        sign = -1.0

    # Bulge formula: tan(included_angle / 4)
    # If angle is near 2*pi, clamp to avoid infinity
    theta_clamped = min(theta, 2.0 * math.pi - 1e-6)
    return sign * math.tan(theta_clamped * 0.25)


def bulge_to_arc(
    p1: Point2D,
    p2: Point2D,
    bulge: float,
    layer: str = "0",
    entity_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Arc2D]:
    """
    Converts a DXF bulge value between p1 and p2 into an Arc2D primitive.
    Returns None if bulge is near zero (straight line).
    """
    if abs(bulge) < 1e-6:
        return None

    chord_len = p1.distance_to(p2)
    if chord_len < 1e-6:
        return None

    theta = 4.0 * math.atan(bulge)
    radius = abs(chord_len / (2.0 * math.sin(theta * 0.5)))

    # Midpoint of chord
    mx = (p1.x + p2.x) * 0.5
    my = (p1.y + p2.y) * 0.5

    # Unit normal to chord (rotated 90 deg CCW)
    dx = (p2.x - p1.x) / chord_len
    dy = (p2.y - p1.y) / chord_len
    nx = -dy
    ny = dx

    # Distance from chord midpoint to circle center
    d = (chord_len * 0.5) / math.tan(theta * 0.5)
    cx = mx + nx * d
    cy = my + ny * d
    center = Point2D(cx, cy)

    ang1 = math.atan2(p1.y - cy, p1.x - cx) % (2.0 * math.pi)
    ang2 = math.atan2(p2.y - cy, p2.x - cx) % (2.0 * math.pi)
    is_ccw = bulge > 0.0

    return Arc2D(
        center=center,
        radius=radius,
        start_angle=ang1,
        end_angle=ang2,
        is_ccw=is_ccw,
        layer=layer,
        entity_id=entity_id,
        metadata=dict(metadata or {})
    )


def reflect_polyline_vertices(
    vertices: List[Tuple[float, float, float]],
    axis: SymmetryAxis2D,
    reverse_order: bool = False
) -> List[Tuple[float, float, float]]:
    """
    Reflects a list of (x, y, bulge) vertices across a symmetry axis.
    
    Mathematical rules:
    1. Coordinate reflection: P' = axis.reflect_point(P).
    2. Reflection inverts chirality (CCW -> CW or vice versa).
       If vertex order is preserved (V'0, V'1, ...): b' = -b.
    3. If vertex order is reversed (V'n-1, V'n-2, ...):
       Reversing traversal flips chord direction (which changes bulge sign again),
       AND shifts the edge bulge to the preceding vertex in the new sequence.
       The edge from Vi to Vi+1 becomes an edge from Vi+1 to Vi.
       Therefore, the bulge of the reversed edge is +b_i located at Vi+1.
    """
    n = len(vertices)
    if n == 0:
        return []

    # Reflect all vertex coordinates
    reflected_points = []
    bulges = []
    for x, y, b in vertices:
        pt = axis.reflect_point(Point2D(x, y))
        reflected_points.append(pt)
        bulges.append(b)

    if not reverse_order:
        # Order preserved: simply invert bulge sign due to chirality flip
        return [(p.x, p.y, -b) for p, b in zip(reflected_points, bulges)]
    else:
        # Reverse vertex order
        # For an edge i -> (i+1)%n with bulge b_i:
        # In reversed order, new vertex j = n - 1 - i.
        # The edge now goes from vertex (i+1) to vertex i.
        # Its bulge in the reversed direction is -(-b_i) = +b_i.
        rev_verts: List[Tuple[float, float, float]] = []
        for j in range(n):
            orig_idx = n - 1 - j
            pt = reflected_points[orig_idx]
            # The edge leaving vertex orig_idx in the reversed path is the edge that previously
            # entered orig_idx, i.e., the edge from (orig_idx - 1) % n to orig_idx.
            prev_idx = (orig_idx - 1) % n
            new_bulge = bulges[prev_idx]  # Inverted due to reflection, then inverted due to traversal = original bulge
            rev_verts.append((pt.x, pt.y, new_bulge))
        return rev_verts


def primitives_to_lwpolyline_vertices(
    primitives: List[Union[LineSegment2D, Arc2D]],
    is_closed: bool = True
) -> List[Tuple[float, float, float]]:
    """
    Converts an ordered chain of LineSegment2D and Arc2D into DXF (x, y, bulge) vertices.
    """
    if not primitives:
        return []

    vertices: List[Tuple[float, float, float]] = []
    for i, prim in enumerate(primitives):
        if isinstance(prim, LineSegment2D):
            vertices.append((prim.start.x, prim.start.y, 0.0))
        elif isinstance(prim, Arc2D):
            b = arc_to_bulge(prim.start_point, prim.end_point, prim.center, prim.is_ccw)
            vertices.append((prim.start_point.x, prim.start_point.y, b))

    # If open polyline, append the last end point with bulge 0
    if not is_closed and primitives:
        last = primitives[-1]
        last_pt = last.end if isinstance(last, LineSegment2D) else last.end_point
        vertices.append((last_pt.x, last_pt.y, 0.0))

    return vertices
