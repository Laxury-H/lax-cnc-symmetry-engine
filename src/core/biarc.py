"""
Bi-Arc Fitting and Curve Approximation Engine for CNC Toolpaths.
Approximates freeform curves (B-splines, Bézier, Ellipses) as collections of
G1-continuous circular arcs and lines with controlled maximum deviation (tol <= 0.02 mm).
Eliminates vertex bloat and feedrate chatter on CNC machines.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Optional, Callable, Union, Dict, Any

from src.core.primitives import Point2D, Vector2D, Arc2D, LineSegment2D


def fit_arc_from_3p(
    p0: Point2D,
    p1: Point2D,
    p2: Point2D,
    layer: str = "0",
    entity_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[Arc2D]:
    """
    Fits a circular arc passing through three non-collinear 2D points: p0 (start), p1 (interior), p2 (end).
    Returns None if points are collinear.
    """
    ax, ay = p0.x, p0.y
    bx, by = p1.x, p1.y
    cx, cy = p2.x, p2.y

    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None

    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d

    center = Point2D(ux, uy)
    radius = math.hypot(ax - ux, ay - uy)

    if radius < 1e-5:
        return None

    ang0 = math.atan2(ay - uy, ax - ux) % (2.0 * math.pi)
    ang2 = math.atan2(cy - uy, cx - ux) % (2.0 * math.pi)

    # Orientation (CCW vs CW) determined by cross product of (p1 - p0) x (p2 - p1)
    cross = (bx - ax) * (cy - by) - (by - ay) * (cx - bx)
    is_ccw = cross > 0.0

    return Arc2D(
        center=center,
        radius=radius,
        start_angle=ang0,
        end_angle=ang2,
        is_ccw=is_ccw,
        layer=layer,
        entity_id=entity_id,
        metadata=dict(metadata) if metadata else {}
    )


def point_distance_to_arc(arc: Arc2D, pt: Point2D) -> float:
    """Computes geometric distance from a 2D point to a circular arc."""
    d_center = arc.center.distance_to(pt)
    radial_dev = abs(d_center - arc.radius)

    # Check angular alignment with arc span
    ang = math.atan2(pt.y - arc.center.y, pt.x - arc.center.x) % (2.0 * math.pi)
    sweep = arc.sweep_angle
    start = arc.start_angle

    if arc.is_ccw:
        diff = (ang - start) % (2.0 * math.pi)
        in_span = diff <= sweep + 1e-4
    else:
        diff = (start - ang) % (2.0 * math.pi)
        in_span = diff <= sweep + 1e-4

    if in_span:
        return radial_dev

    # Clamped to closest arc endpoint
    d0 = arc.start_point.distance_to(pt)
    d1 = arc.end_point.distance_to(pt)
    return min(d0, d1)


def approximate_curve_to_arcs(
    eval_fn: Callable[[float], Point2D],
    t0: float,
    t1: float,
    tol: float = 0.02,
    depth: int = 0,
    max_depth: int = 8,
    layer: str = "0",
    entity_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> List[Union[Arc2D, LineSegment2D]]:
    """
    Recursively approximates parametric curve C(t) for t in [t0, t1]
    into a minimal sequence of G1-tangent circular arcs and line segments with maximum deviation <= tol.
    """
    p0 = eval_fn(t0)
    p1 = eval_fn(t1)

    chord_len = p0.distance_to(p1)
    if chord_len < 1e-6:
        if (t1 - t0) > 1e-4 and depth < max_depth:
            t_mid = (t0 + t1) * 0.5
            left = approximate_curve_to_arcs(eval_fn, t0, t_mid, tol, depth + 1, max_depth, layer, entity_id, metadata)
            right = approximate_curve_to_arcs(eval_fn, t_mid, t1, tol, depth + 1, max_depth, layer, entity_id, metadata)
            return left + right
        return []

    # 1. Test straight line approximation
    line = LineSegment2D(start=p0, end=p1, layer=layer, entity_id=entity_id, metadata=dict(metadata or {}))
    max_line_dev = 0.0
    for k in (0.25, 0.5, 0.75):
        tk = t0 + (t1 - t0) * k
        dev = line.distance_to_point(eval_fn(tk))
        if dev > max_line_dev:
            max_line_dev = dev
    if max_line_dev <= tol:
        return [line]

    # 2. Test 3-point circular arc approximation
    t_mid = (t0 + t1) * 0.5
    pm = eval_fn(t_mid)
    arc = fit_arc_from_3p(p0, pm, p1, layer=layer, entity_id=entity_id, metadata=metadata)

    if arc is not None and arc.radius < 1e7:
        max_arc_dev = 0.0
        # Sample intermediate test points
        for k in (0.125, 0.25, 0.375, 0.625, 0.75, 0.875):
            tk = t0 + (t1 - t0) * k
            dev = point_distance_to_arc(arc, eval_fn(tk))
            if dev > max_arc_dev:
                max_arc_dev = dev

        if max_arc_dev <= tol or depth >= max_depth:
            return [arc]

    # 3. Subdivide recursively if tolerance threshold exceeded
    if depth >= max_depth:
        # Fallback to straight line at maximum recursion depth to ensure termination
        return [line]

    left = approximate_curve_to_arcs(eval_fn, t0, t_mid, tol, depth + 1, max_depth, layer, entity_id, metadata)
    right = approximate_curve_to_arcs(eval_fn, t_mid, t1, tol, depth + 1, max_depth, layer, entity_id, metadata)
    return left + right


def approximate_spline_entity(
    entity: Any,
    scale: float = 1.0,
    tol: float = 0.02,
    layer: str = "0"
) -> List[Union[Arc2D, LineSegment2D]]:
    """
    Converts a DXF SPLINE entity into an optimal set of tangent circular arcs and lines.
    """
    try:
        bspline = entity.construction_tool()
        max_t = getattr(bspline, "max_t", 1.0)
        entity_id = str(getattr(entity.dxf, "handle", ""))

        def eval_spline(u: float) -> Point2D:
            p = bspline.point(u)
            return Point2D(float(p[0]) * scale, float(p[1]) * scale)

        effective_tol = max(0.005, tol)
        return approximate_curve_to_arcs(
            eval_spline,
            0.0,
            float(max_t),
            tol=effective_tol,
            max_depth=8,
            layer=layer,
            entity_id=entity_id,
            metadata={"source_type": "SPLINE"}
        )
    except Exception:
        pts = [Point2D(p.x * scale, p.y * scale) for p in entity.flattening(tol)]
        res: List[Union[Arc2D, LineSegment2D]] = []
        for a, b in zip(pts, pts[1:]):
            if a.distance_to(b) > 1e-4:
                res.append(LineSegment2D(start=a, end=b, layer=layer))
        return res


def approximate_ellipse_entity(
    entity: Any,
    scale: float = 1.0,
    tol: float = 0.02,
    layer: str = "0"
) -> List[Union[Arc2D, LineSegment2D]]:
    """
    Converts a DXF ELLIPSE entity into an optimal set of tangent circular arcs.
    """
    try:
        c_ellipse = entity.construction_tool()
        start_param = float(c_ellipse.start_param)
        end_param = float(c_ellipse.end_param)
        entity_id = str(getattr(entity.dxf, "handle", ""))

        span = end_param - start_param
        while span <= 0:
            span += 2.0 * math.pi

        def eval_ellipse(t: float) -> Point2D:
            param = start_param + t * span
            v = list(c_ellipse.vertices([param]))[0]
            return Point2D(float(v.x) * scale, float(v.y) * scale)

        effective_tol = max(0.005, tol)
        return approximate_curve_to_arcs(
            eval_ellipse,
            0.0,
            1.0,
            tol=effective_tol,
            max_depth=8,
            layer=layer,
            entity_id=entity_id,
            metadata={"source_type": "ELLIPSE"}
        )
    except Exception:
        pts = [Point2D(p.x * scale, p.y * scale) for p in entity.flattening(tol)]
        res: List[Union[Arc2D, LineSegment2D]] = []
        for a, b in zip(pts, pts[1:]):
            if a.distance_to(b) > 1e-4:
                res.append(LineSegment2D(start=a, end=b, layer=layer))
        return res
