"""
Geometric constraint definitions for design intent regularization.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Any, Dict

from src.core.primitives import Point2D, LineSegment2D


class ConstraintType(Enum):
    COLLINEAR = "COLLINEAR"
    PARALLEL = "PARALLEL"
    PERPENDICULAR = "PERPENDICULAR"
    EQUAL_SPACING = "EQUAL_SPACING"
    EQUAL_LENGTH = "EQUAL_LENGTH"
    EQUAL_DIMENSION = "EQUAL_DIMENSION"
    FIXED_ANCHOR = "FIXED_ANCHOR"
    SYMMETRIC_PAIR = "SYMMETRIC_PAIR"


class ConstraintStrictness(Enum):
    FIXED = "FIXED"       # Hard constraint, cannot be violated
    SOFT = "SOFT"         # Optimization target, balance with others
    OPTIONAL = "OPTIONAL" # Minor aesthetic preference


@dataclass
class GeometricConstraint:
    """Base class for geometric constraints."""
    constraint_id: str
    constraint_type: ConstraintType
    strictness: ConstraintStrictness
    weight: float = 1.0
    description: str = ""

    def evaluate_residual(self) -> float:
        """Returns deviation or residual error of constraint (0 = perfectly satisfied)."""
        return 0.0


@dataclass
class CollinearConstraint(GeometricConstraint):
    """Two or more segments intended to lie on the same infinite line."""
    feature_ids: List[str] = field(default_factory=list)
    canonical_offset: float = 0.0
    canonical_angle_deg: float = 0.0


@dataclass
class ParallelConstraint(GeometricConstraint):
    """Two or more segments intended to be parallel."""
    feature_ids: List[str] = field(default_factory=list)
    target_angle_deg: float = 0.0


@dataclass
class PerpendicularConstraint(GeometricConstraint):
    """Two segments or lines intended to meet at 90 degrees."""
    feature_id_1: str = ""
    feature_id_2: str = ""


@dataclass
class EqualSpacingConstraint(GeometricConstraint):
    """A set of adjacent parallel channels intended to share a uniform kerf width."""
    pair_feature_ids: List[Tuple[str, str]] = field(default_factory=list)
    target_spacing_mm: float = 0.0
    tolerance_mm: float = 0.5


@dataclass
class EqualDimensionConstraint(GeometricConstraint):
    """Two or more motifs/boxes intended to share identical width and height."""
    motif_ids: List[str] = field(default_factory=list)
    target_width: float = 0.0
    target_height: float = 0.0
