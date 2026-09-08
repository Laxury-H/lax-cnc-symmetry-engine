"""
Design intent and constraint detection package.
Infers geometric intentions (canonical angles, uniform spacings, collinearity, symmetry).
"""

from src.intent.constraints import (
    ConstraintType,
    ConstraintStrictness,
    GeometricConstraint,
    CollinearConstraint,
    ParallelConstraint,
    PerpendicularConstraint,
    EqualSpacingConstraint,
    EqualDimensionConstraint
)
from src.intent.detector import (
    DesignIntentReport,
    DesignIntentDetector
)

__all__ = [
    "ConstraintType",
    "ConstraintStrictness",
    "GeometricConstraint",
    "CollinearConstraint",
    "ParallelConstraint",
    "PerpendicularConstraint",
    "EqualSpacingConstraint",
    "EqualDimensionConstraint",
    "DesignIntentReport",
    "DesignIntentDetector"
]
