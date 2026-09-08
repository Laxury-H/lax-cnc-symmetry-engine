"""
Bounding box utilities in 2D and 3D.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
from src.core.primitives import Point2D, BoundingBox2D


@dataclass(frozen=True, slots=True)
class Point3D:
    x: float
    y: float
    z: float

    def distance_to(self, other: Point3D) -> float:
        import math
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2 + (self.z - other.z)**2)


@dataclass(frozen=True, slots=True)
class BoundingBox3D:
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def width(self) -> float:
        return max(0.0, self.max_x - self.min_x)

    @property
    def height(self) -> float:
        return max(0.0, self.max_y - self.min_y)

    @property
    def depth(self) -> float:
        return max(0.0, self.max_z - self.min_z)

    @property
    def center(self) -> Point3D:
        return Point3D(
            (self.min_x + self.max_x) * 0.5,
            (self.min_y + self.max_y) * 0.5,
            (self.min_z + self.max_z) * 0.5
        )

    def to_2d(self) -> BoundingBox2D:
        return BoundingBox2D(self.min_x, self.min_y, self.max_x, self.max_y)


__all__ = ["BoundingBox2D", "BoundingBox3D", "Point3D"]
