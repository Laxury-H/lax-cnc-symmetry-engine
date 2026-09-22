"""
C1 / G1 Continuity and Axis Boundary Constraint Enforcement Engine.
Enforces first-order tangency constraints at symmetry axis intersections:
If a curve or segment intersects or ends near the symmetry axis with a tangent
deviating by <= 5 degrees from perpendicular, it is automatically snapped strictly
perpendicular (90.00 deg) to the axis.
This guarantees absolute C1/G1 smoothness across the reflection boundary, eliminating
micro-kinks, axis feedrate drops, and tool burns in CNC machining.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Optional, Union

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D
from src.core.transform import SymmetryAxis2D


class AxisContinuityEnforcer:
    """
    Ensures that geometric curves meeting or crossing a symmetry axis
    do so at strictly perpendicular angles (90 deg), avoiding microscopic kinks when mirrored.
    """

    def __init__(
        self,
        axis: Optional[SymmetryAxis2D] = None,
        angle_threshold_deg: float = 5.0,
        snap_distance_mm: float = 0.20,
        snap_angle_threshold_deg: Optional[float] = None
    ):
        if snap_angle_threshold_deg is not None:
            angle_threshold_deg = snap_angle_threshold_deg
        self.axis = axis
        self.angle_threshold_rad = math.radians(angle_threshold_deg)
        self.snap_distance_mm = snap_distance_mm

    def enforce_line_continuity(
        self,
        line: LineSegment2D,
        axis: Optional[SymmetryAxis2D] = None
    ) -> LineSegment2D:
        """
        Enforces G1 perpendicularity for a line segment ending near the symmetry axis.
        """
        ax = axis or self.axis
        if ax is None:
            return line

        d_start = abs(ax.distance_to_point(line.start))
        d_end = abs(ax.distance_to_point(line.end))

        v = line.end - line.start
        if v.length < 1e-4:
            return line

        norm = ax.normal
        dot = v.normalized().dot(norm)
        dev = math.acos(max(-1.0, min(1.0, abs(dot))))

        if dev <= self.angle_threshold_rad:
            if d_end <= self.snap_distance_mm:
                # End is at the axis: snap end to exact normal projection of start
                new_end = ax.project_point(line.start)
                return LineSegment2D(
                    start=line.start,
                    end=new_end,
                    layer=line.layer,
                    entity_id=line.entity_id,
                    metadata=dict(line.metadata)
                )
            elif d_start <= self.snap_distance_mm:
                # Start is at the axis: snap start to exact normal projection of end
                new_start = ax.project_point(line.end)
                return LineSegment2D(
                    start=new_start,
                    end=line.end,
                    layer=line.layer,
                    entity_id=line.entity_id,
                    metadata=dict(line.metadata)
                )

        return line

    enforce_continuity_line = enforce_line_continuity

    def enforce_arc_continuity(
        self,
        arc: Arc2D,
        axis: SymmetryAxis2D
    ) -> Arc2D:
        """
        Enforces G1 perpendicularity for an arc ending near the symmetry axis.
        At the intersection point, the tangent must be perpendicular to the axis,
        meaning the radial vector (center -> P_axis) must be parallel to the axis direction.
        """
        p_start = arc.start_point
        p_end = arc.end_point

        d_start = abs(axis.distance_to_point(p_start))
        d_end = abs(axis.distance_to_point(p_end))

        # Handle start point on axis
        if d_start <= self.snap_distance_mm:
            p_axis = axis.project_point(p_start)
            # Tangent at start point
            t_ang = arc.start_angle + (math.pi * 0.5 if arc.is_ccw else -math.pi * 0.5)
            tan_vec = Vector2D(math.cos(t_ang), math.sin(t_ang))
            norm = axis.normal
            dot = tan_vec.dot(norm)
            dev = min(math.acos(max(-1.0, min(1.0, abs(dot)))), math.pi * 0.5)
            if dev <= self.angle_threshold_rad:
                # Radial vector must be strictly along axis direction
                # Project center onto line parallel to axis passing through p_axis
                v_axis = axis.direction
                # Center should have same normal projection as p_axis
                center_proj = axis.project_point(arc.center)
                along_axis = (arc.center - center_proj).dot(v_axis)
                # Shift center so that p_axis - center is strictly parallel to axis.direction
                new_center = p_axis + (v_axis * (-along_axis if abs(along_axis) > 1e-4 else -arc.radius))
                new_radius = new_center.distance_to(p_axis)
                v_s = p_axis - new_center
                v_e = p_end - new_center
                new_start_ang = math.atan2(v_s.dy, v_s.dx) % (2.0 * math.pi)
                new_end_ang = math.atan2(v_e.dy, v_e.dx) % (2.0 * math.pi)
                return Arc2D(
                    center=new_center,
                    radius=new_radius,
                    start_angle=new_start_ang,
                    end_angle=new_end_ang,
                    is_ccw=arc.is_ccw,
                    layer=arc.layer,
                    entity_id=arc.entity_id,
                    metadata=dict(arc.metadata)
                )

        # Handle end point on axis
        if d_end <= self.snap_distance_mm:
            p_axis = axis.project_point(p_end)
            t_ang = arc.end_angle + (math.pi * 0.5 if arc.is_ccw else -math.pi * 0.5)
            tan_vec = Vector2D(math.cos(t_ang), math.sin(t_ang))
            norm = axis.normal
            dot = tan_vec.dot(norm)
            dev = min(math.acos(max(-1.0, min(1.0, abs(dot)))), math.pi * 0.5)
            if dev <= self.angle_threshold_rad:
                v_axis = axis.direction
                center_proj = axis.project_point(arc.center)
                along_axis = (arc.center - center_proj).dot(v_axis)
                new_center = p_axis + (v_axis * (-along_axis if abs(along_axis) > 1e-4 else -arc.radius))
                new_radius = new_center.distance_to(p_axis)
                v_s = p_start - new_center
                v_e = p_axis - new_center
                new_start_ang = math.atan2(v_s.dy, v_s.dx) % (2.0 * math.pi)
                new_end_ang = math.atan2(v_e.dy, v_e.dx) % (2.0 * math.pi)
                return Arc2D(
                    center=new_center,
                    radius=new_radius,
                    start_angle=new_start_ang,
                    end_angle=new_end_ang,
                    is_ccw=arc.is_ccw,
                    layer=arc.layer,
                    entity_id=arc.entity_id,
                    metadata=dict(arc.metadata)
                )

        return arc

    def enforce_model_continuity(
        self,
        lines: List[LineSegment2D],
        arcs: List[Arc2D],
        axis: SymmetryAxis2D
    ) -> Tuple[List[LineSegment2D], List[Arc2D]]:
        """Applies G1 continuity enforcement to all primitives near the symmetry axis."""
        adjusted_lines = [self.enforce_line_continuity(l, axis) for l in lines]
        adjusted_arcs = [self.enforce_arc_continuity(a, axis) for a in arcs]
        return (adjusted_lines, adjusted_arcs)
