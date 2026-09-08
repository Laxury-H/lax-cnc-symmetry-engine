"""Core geometry primitives and transformations."""

from src.core.primitives import (
    Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D
)
from src.core.transform import (
    SymmetryAxis2D, AffineTransform2D
)
from src.core.bbox import Point3D, BoundingBox3D

__all__ = [
    "Point2D", "Vector2D", "LineSegment2D", "Arc2D", "Circle2D", "BoundingBox2D",
    "Point3D", "BoundingBox3D",
    "SymmetryAxis2D", "AffineTransform2D"
]
