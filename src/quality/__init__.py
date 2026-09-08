"""
Visual quality and regularity scoring package.
Combines symmetry, spacing consistency, alignment, angle regularity,
proportions, and deformation penalty into a holistic aesthetic score (0-100).
"""

from src.quality.scorer import (
    VisualQualityScore,
    VisualQualityScorer
)

__all__ = [
    "VisualQualityScore",
    "VisualQualityScorer"
]
