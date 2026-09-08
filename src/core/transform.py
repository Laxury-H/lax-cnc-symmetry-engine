"""
Affine transformations and symmetry reflection operations in 2D.
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Tuple, Union
import numpy as np

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D


@dataclass(frozen=True)
class SymmetryAxis2D:
    """
    Infinite 2D symmetry line.
    Represented as a point on the line P0 and unit direction vector u (or angle theta with x-axis).
    Equation: normal.x * x + normal.y * y + d = 0.
    """
    origin: Point2D
    direction: Vector2D  # Normalized direction along axis

    def __post_init__(self):
        norm_dir = self.direction.normalized()
        # Force standard direction orientation: angle in [0, pi)
        ang = norm_dir.angle % math.pi
        std_dir = Vector2D(math.cos(ang), math.sin(ang))
        object.__setattr__(self, "direction", std_dir)

    @property
    def angle(self) -> float:
        """Angle with positive X-axis in radians in [0, pi)."""
        return self.direction.angle % math.pi

    @property
    def angle_degrees(self) -> float:
        return math.degrees(self.angle)

    @property
    def normal(self) -> Vector2D:
        """Unit normal vector to the axis."""
        return self.direction.perpendicular()

    @property
    def is_vertical(self) -> bool:
        """True if within 0.1 degree of vertical (pi/2)."""
        return abs(self.angle - math.pi / 2) < math.radians(0.1)

    @property
    def is_horizontal(self) -> bool:
        """True if within 0.1 degree of horizontal (0 or pi)."""
        ang = self.angle
        return ang < math.radians(0.1) or abs(ang - math.pi) < math.radians(0.1)

    def distance_to_point(self, pt: Point2D) -> float:
        """Signed perpendicular distance from line to point."""
        v = pt - self.origin
        return v.cross(self.direction)

    def project_point(self, pt: Point2D) -> Point2D:
        """Orthogonal projection of point onto the axis."""
        v = pt - self.origin
        proj_len = v.dot(self.direction)
        return self.origin + (self.direction * proj_len)

    def reflect_point(self, pt: Point2D) -> Point2D:
        """Reflect a 2D point across this symmetry axis."""
        proj = self.project_point(pt)
        # P_reflected = 2 * proj - P = P + 2 * (proj - P)
        return Point2D(2.0 * proj.x - pt.x, 2.0 * proj.y - pt.y)

    def reflect_vector(self, v: Vector2D) -> Vector2D:
        """Reflect a direction vector across this axis."""
        proj_len = v.dot(self.direction)
        v_proj = self.direction * proj_len
        return Vector2D(2.0 * v_proj.dx - v.dx, 2.0 * v_proj.dy - v.dy)

    def reflect_line(self, line: LineSegment2D) -> LineSegment2D:
        """Reflect line segment across axis."""
        return LineSegment2D(
            start=self.reflect_point(line.start),
            end=self.reflect_point(line.end),
            layer=line.layer,
            metadata=dict(line.metadata)
        )

    def reflect_arc(self, arc: Arc2D) -> Arc2D:
        """Reflect arc across axis. Note: Reflection inverts chirality (CCW <-> CW)."""
        refl_center = self.reflect_point(arc.center)
        refl_start = self.reflect_point(arc.start_point)
        refl_end = self.reflect_point(arc.end_point)

        # Angles from reflected center
        v_start = refl_start - refl_center
        v_end = refl_end - refl_center
        new_start_angle = v_start.angle % (2 * math.pi)
        new_end_angle = v_end.angle % (2 * math.pi)

        # Reflection reverses CCW to CW or vice-versa
        # In standard CAD, we usually represent arcs CCW, so we can swap start/end if needed
        # or flip the ccw flag
        return Arc2D(
            center=refl_center,
            radius=arc.radius,
            start_angle=new_start_angle,
            end_angle=new_end_angle,
            is_ccw=not arc.is_ccw,
            layer=arc.layer,
            metadata=dict(arc.metadata)
        )

    def reflect_circle(self, circle: Circle2D) -> Circle2D:
        """Reflect circle across axis."""
        return Circle2D(
            center=self.reflect_point(circle.center),
            radius=circle.radius,
            layer=circle.layer,
            metadata=dict(circle.metadata)
        )

    @classmethod
    def vertical(cls, x_offset: float) -> SymmetryAxis2D:
        """Create a vertical symmetry axis x = x_offset."""
        return cls(origin=Point2D(x_offset, 0.0), direction=Vector2D(0.0, 1.0))

    @classmethod
    def horizontal(cls, y_offset: float) -> SymmetryAxis2D:
        """Create a horizontal symmetry axis y = y_offset."""
        return cls(origin=Point2D(0.0, y_offset), direction=Vector2D(1.0, 0.0))

    @classmethod
    def from_angle_and_point(cls, pt: Point2D, angle_radians: float) -> SymmetryAxis2D:
        """Create axis passing through pt with specified angle."""
        return cls(origin=pt, direction=Vector2D(math.cos(angle_radians), math.sin(angle_radians)))


class AffineTransform2D:
    """3x3 affine transformation matrix for 2D geometry operations."""

    def __init__(self, matrix: Optional[np.ndarray] = None):
        if matrix is None:
            self.m = np.eye(3, dtype=np.float64)
        else:
            self.m = np.array(matrix, dtype=np.float64)

    def apply_point(self, pt: Point2D) -> Point2D:
        vec = np.array([pt.x, pt.y, 1.0], dtype=np.float64)
        res = self.m @ vec
        return Point2D(float(res[0]), float(res[1]))

    def apply_vector(self, v: Vector2D) -> Vector2D:
        vec = np.array([v.dx, v.dy, 0.0], dtype=np.float64)
        res = self.m @ vec
        return Vector2D(float(res[0]), float(res[1]))

    def compose(self, other: AffineTransform2D) -> AffineTransform2D:
        """Returns new transform representing self applied AFTER other: T = self * other."""
        return AffineTransform2D(self.m @ other.m)

    @classmethod
    def translation(cls, dx: float, dy: float) -> AffineTransform2D:
        m = np.eye(3, dtype=np.float64)
        m[0, 2] = dx
        m[1, 2] = dy
        return cls(m)

    @classmethod
    def rotation(cls, angle_radians: float, center: Optional[Point2D] = None) -> AffineTransform2D:
        cos_a = math.cos(angle_radians)
        sin_a = math.sin(angle_radians)
        if center is None or (center.x == 0.0 and center.y == 0.0):
            m = np.array([
                [cos_a, -sin_a, 0.0],
                [sin_a,  cos_a, 0.0],
                [0.0,    0.0,   1.0]
            ], dtype=np.float64)
            return cls(m)
        t1 = cls.translation(-center.x, -center.y)
        rot = cls.rotation(angle_radians)
        t2 = cls.translation(center.x, center.y)
        return t2.compose(rot).compose(t1)

    @classmethod
    def scaling(cls, sx: float, sy: float, center: Optional[Point2D] = None) -> AffineTransform2D:
        if center is None or (center.x == 0.0 and center.y == 0.0):
            m = np.array([
                [sx,  0.0, 0.0],
                [0.0, sy,  0.0],
                [0.0, 0.0, 1.0]
            ], dtype=np.float64)
            return cls(m)
        t1 = cls.translation(-center.x, -center.y)
        scale = cls.scaling(sx, sy)
        t2 = cls.translation(center.x, center.y)
        return t2.compose(scale).compose(t1)
