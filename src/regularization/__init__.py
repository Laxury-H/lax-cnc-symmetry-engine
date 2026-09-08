"""
Geometric regularization package.
Eliminates kinks ("móp méo"), regularizes angles and spacings,
and reconstructs canonical motifs with constrained repositioning.
"""

from src.regularization.angle_regularizer import AngleRegularizer
from src.regularization.deformation_detector import DeformationDetector, DeformationReport
from src.regularization.canonical_motif import CanonicalMotifReconstructor

__all__ = [
    "AngleRegularizer",
    "DeformationDetector",
    "DeformationReport",
    "CanonicalMotifReconstructor"
]
