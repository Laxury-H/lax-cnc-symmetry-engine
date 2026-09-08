"""
Geometric primitives for 2D CAD/CAM computation.
All linear dimensions in millimeters (mm), angles in radians (internally) with degree helpers.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any


@dataclass(frozen=True, slots=True)
class Point2D:
    """Immutable 2D point with high precision and tolerance-aware operations."""
    x: float
    y: float

    def to_tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)

    def distance_to(self, other: Point2D) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def distance_sq(self, other: Point2D) -> float:
        dx = self.x - other.x
        dy = self.y - other.y
        return dx * dx + dy * dy

    def is_close(self, other: Point2D, tol: float = 1e-4) -> bool:
        return self.distance_to(other) <= tol

    def quantize(self, tol: float = 0.05) -> Tuple[int, int]:
        """Quantized coordinate key for spatial hash / graph node identification."""
        return (round(self.x / tol), round(self.y / tol))

    def __add__(self, v: Vector2D) -> Point2D:
        return Point2D(self.x + v.dx, self.y + v.dy)

    def __sub__(self, other: Point2D | Vector2D) -> Vector2D | Point2D:
        if isinstance(other, Point2D):
            return Vector2D(self.x - other.x, self.y - other.y)
        return Point2D(self.x - other.dx, self.y - other.dy)

    def to_dict(self) -> Dict[str, float]:
        return {"x": round(self.x, 6), "y": round(self.y, 6)}

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> Point2D:
        return cls(float(data["x"]), float(data["y"]))


@dataclass(frozen=True, slots=True)
class Vector2D:
    """2D direction / displacement vector."""
    dx: float
    dy: float

    @property
    def length(self) -> float:
        return math.hypot(self.dx, self.dy)

    @property
    def length_sq(self) -> float:
        return self.dx * self.dx + self.dy * self.dy

    @property
    def angle(self) -> float:
        """Angle in radians in [-pi, pi]."""
        return math.atan2(self.dy, self.dx)

    def normalized(self) -> Vector2D:
        l = self.length
        if l < 1e-12:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.dx / l, self.dy / l)

    def dot(self, other: Vector2D) -> float:
        return self.dx * other.dx + self.dy * other.dy

    def cross(self, other: Vector2D) -> float:
        """2D cross product: z-component of (dx1, dy1, 0) x (dx2, dy2, 0)."""
        return self.dx * other.dy - self.dy * other.dx

    def angle_with(self, other: Vector2D) -> float:
        """Angle between two vectors in radians [0, pi]."""
        u1 = self.normalized()
        u2 = other.normalized()
        dot = max(-1.0, min(1.0, u1.dot(u2)))
        return math.acos(dot)

    def perpendicular(self) -> Vector2D:
        """Vector rotated 90 degrees counter-clockwise."""
        return Vector2D(-self.dy, self.dx)

    def __mul__(self, scalar: float) -> Vector2D:
        return Vector2D(self.dx * scalar, self.dy * scalar)

    def __rmul__(self, scalar: float) -> Vector2D:
        return self.__mul__(scalar)

    def __add__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.dx + other.dx, self.dy + other.dy)

    def __sub__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.dx - other.dx, self.dy - other.dy)

    def __neg__(self) -> Vector2D:
        return Vector2D(-self.dx, -self.dy)


@dataclass(frozen=True, slots=True)
class BoundingBox2D:
    """Axis-aligned 2D bounding box."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return max(0.0, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        return max(0.0, self.max_y - self.min_y)

    @property
    def center(self) -> Point2D:
        return Point2D((self.min_x + self.max_x) * 0.5, (self.min_y + self.max_y) * 0.5)

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains_point(self, pt: Point2D, tol: float = 1e-6) -> bool:
        return (self.min_x - tol <= pt.x <= self.max_x + tol and
                self.min_y - tol <= pt.y <= self.max_y + tol)

    def intersects(self, other: BoundingBox2D, tol: float = 1e-6) -> bool:
        return not (self.max_x + tol < other.min_x or
                    self.min_x - tol > other.max_x or
                    self.max_y + tol < other.min_y or
                    self.min_y - tol > other.max_y)

    def expand_by(self, other: BoundingBox2D) -> BoundingBox2D:
        return BoundingBox2D(
            min(self.min_x, other.min_x),
            min(self.min_y, other.min_y),
            max(self.max_x, other.max_x),
            max(self.max_y, other.max_y)
        )

    def expand_point(self, pt: Point2D) -> BoundingBox2D:
        return BoundingBox2D(
            min(self.min_x, pt.x),
            min(self.min_y, pt.y),
            max(self.max_x, pt.x),
            max(self.max_y, pt.y)
        )

    @classmethod
    def from_points(cls, points: List[Point2D]) -> BoundingBox2D:
        if not points:
            return cls(0.0, 0.0, 0.0, 0.0)
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        return cls(min(xs), min(ys), max(xs), max(ys))


@dataclass
class LineSegment2D:
    """Directed 2D line segment between two endpoints."""
    start: Point2D
    end: Point2D
    layer: str = "0"
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def length(self) -> float:
        return self.start.distance_to(self.end)

    @property
    def midpoint(self) -> Point2D:
        return Point2D((self.start.x + self.end.x) * 0.5, (self.start.y + self.end.y) * 0.5)

    @property
    def vector(self) -> Vector2D:
        return self.end - self.start

    @property
    def direction(self) -> Vector2D:
        return self.vector.normalized()

    @property
    def angle(self) -> float:
        """Angle in radians [-pi, pi]."""
        return self.vector.angle

    @property
    def bbox(self) -> BoundingBox2D:
        return BoundingBox2D(
            min(self.start.x, self.end.x),
            min(self.start.y, self.end.y),
            max(self.start.x, self.end.x),
            max(self.start.y, self.end.y)
        )

    def distance_to_point(self, pt: Point2D) -> float:
        """Perpendicular distance to segment clamped to endpoints."""
        v = self.vector
        l_sq = v.length_sq
        if l_sq < 1e-12:
            return self.start.distance_to(pt)
        w = pt - self.start
        t = max(0.0, min(1.0, w.dot(v) / l_sq))
        projection = self.start + (t * v)
        return pt.distance_to(projection)

    def project_point(self, pt: Point2D) -> Tuple[Point2D, float]:
        """Project point onto segment. Returns (projected_point, t in [0, 1])."""
        v = self.vector
        l_sq = v.length_sq
        if l_sq < 1e-12:
            return (self.start, 0.0)
        w = pt - self.start
        t = max(0.0, min(1.0, w.dot(v) / l_sq))
        proj = self.start + (t * v)
        return (proj, t)

    def reversed(self) -> LineSegment2D:
        return LineSegment2D(
            start=self.end,
            end=self.start,
            layer=self.layer,
            entity_id=self.entity_id,
            metadata=dict(self.metadata)
        )

    def sample_points(self, num_points: int = 10) -> List[Point2D]:
        """Sample points along segment uniformly."""
        if num_points <= 1:
            return [self.midpoint]
        pts = []
        v = self.vector
        for i in range(num_points):
            t = i / (num_points - 1)
            pts.append(self.start + (t * v))
        return pts

    def is_coincident(self, other: LineSegment2D, tol: float = 0.05) -> bool:
        """Check if segments match in either forward or reverse direction."""
        fwd = self.start.is_close(other.start, tol) and self.end.is_close(other.end, tol)
        rev = self.start.is_close(other.end, tol) and self.end.is_close(other.start, tol)
        return fwd or rev

    def intersection_point(self, other: LineSegment2D) -> Optional[Point2D]:
        """Compute intersection point between two line segments if they intersect."""
        p = self.start
        r = self.vector
        q = other.start
        s = other.vector

        r_cross_s = r.cross(s)
        if abs(r_cross_s) < 1e-9:
            return None  # Parallel or collinear

        q_minus_p = q - p
        t = q_minus_p.cross(s) / r_cross_s
        u = q_minus_p.cross(r) / r_cross_s

        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return p + (r * t)
        return None

    def intersects(self, other: LineSegment2D) -> bool:
        """True if two segments intersect."""
        return self.intersection_point(other) is not None


@dataclass
class Arc2D:
    """Circular arc in 2D defined by center, radius, start angle, and end angle (radians)."""
    center: Point2D
    radius: float
    start_angle: float  # radians [0, 2*pi)
    end_angle: float    # radians [0, 2*pi)
    is_ccw: bool = True
    layer: str = "0"
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def sweep_angle(self) -> float:
        """Sweep angle in radians > 0."""
        diff = self.end_angle - self.start_angle
        if self.is_ccw:
            while diff < 0:
                diff += 2 * math.pi
        else:
            while diff > 0:
                diff -= 2 * math.pi
            diff = abs(diff)
        return diff

    @property
    def length(self) -> float:
        return self.radius * self.sweep_angle

    @property
    def start_point(self) -> Point2D:
        return Point2D(
            self.center.x + self.radius * math.cos(self.start_angle),
            self.center.y + self.radius * math.sin(self.start_angle)
        )

    @property
    def end_point(self) -> Point2D:
        return Point2D(
            self.center.x + self.radius * math.cos(self.end_angle),
            self.center.y + self.radius * math.sin(self.end_angle)
        )

    @property
    def midpoint(self) -> Point2D:
        mid_ang = self.start_angle + (0.5 * self.sweep_angle if self.is_ccw else -0.5 * self.sweep_angle)
        return Point2D(
            self.center.x + self.radius * math.cos(mid_ang),
            self.center.y + self.radius * math.sin(mid_ang)
        )

    def sample_points(self, num_points: int = 16) -> List[Point2D]:
        """Sample points along arc contour."""
        if num_points <= 1:
            return [self.midpoint]
        pts = []
        sweep = self.sweep_angle
        sign = 1.0 if self.is_ccw else -1.0
        for i in range(num_points):
            t = i / (num_points - 1)
            ang = self.start_angle + sign * t * sweep
            pts.append(Point2D(
                self.center.x + self.radius * math.cos(ang),
                self.center.y + self.radius * math.sin(ang)
            ))
        return pts

    @property
    def bbox(self) -> BoundingBox2D:
        pts = self.sample_points(24)
        return BoundingBox2D.from_points(pts)


@dataclass
class Circle2D:
    """Full circle in 2D."""
    center: Point2D
    radius: float
    layer: str = "0"
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def diameter(self) -> float:
        return self.radius * 2.0

    @property
    def perimeter(self) -> float:
        return 2.0 * math.pi * self.radius

    @property
    def area(self) -> float:
        return math.pi * self.radius * self.radius

    @property
    def bbox(self) -> BoundingBox2D:
        return BoundingBox2D(
            self.center.x - self.radius,
            self.center.y - self.radius,
            self.center.x + self.radius,
            self.center.y + self.radius
        )

    def sample_points(self, num_points: int = 32) -> List[Point2D]:
        pts = []
        for i in range(num_points):
            ang = (i / num_points) * 2 * math.pi
            pts.append(Point2D(
                self.center.x + self.radius * math.cos(ang),
                self.center.y + self.radius * math.sin(ang)
            ))
        return pts
