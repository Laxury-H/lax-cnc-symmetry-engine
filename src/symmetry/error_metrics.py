"""
Comprehensive symmetry error metrics for 2D CAD patterns.
Computes point-wise, segment-wise, and loop-wise geometric deviations.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.spatial.index import PointSpatialIndex
from src.topology.cycle_finder import ClosedLoop


@dataclass
class SymmetryErrorProfile:
    """Detailed quantitative error report of geometric symmetry."""
    axis: SymmetryAxis2D
    sample_count: int
    mean_deviation: float          # mm
    rms_deviation: float           # mm
    median_deviation: float        # mm
    max_deviation: float           # mm
    p90_deviation: float           # 90th percentile deviation mm
    hausdorff_distance: float      # mm
    matched_ratio: float           # Ratio of points with counterpart within tolerance
    loop_area_error_ratio: float   # Relative difference in area between mirrored loops
    symmetry_score: float          # 0 to 100
    confidence: float              # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "axis_angle_deg": round(self.axis.angle_degrees, 3),
            "axis_origin": self.axis.origin.to_dict(),
            "mean_deviation_mm": round(self.mean_deviation, 4),
            "rms_deviation_mm": round(self.rms_deviation, 4),
            "median_deviation_mm": round(self.median_deviation, 4),
            "max_deviation_mm": round(self.max_deviation, 4),
            "p90_deviation_mm": round(self.p90_deviation, 4),
            "hausdorff_distance_mm": round(self.hausdorff_distance, 4),
            "matched_ratio": round(self.matched_ratio, 4),
            "loop_area_error_ratio": round(self.loop_area_error_ratio, 4),
            "symmetry_score": round(self.symmetry_score, 2),
            "confidence": round(self.confidence, 4),
        }


class SymmetryEvaluator:
    """Evaluates geometric symmetry of a CAD model or point set across a given axis."""

    def __init__(self, sample_points: List[Point2D], loops: Optional[List[ClosedLoop]] = None, tolerance: float = 0.20):
        self.sample_points = sample_points
        self.spatial_index = PointSpatialIndex(sample_points)
        self.loops = loops or []
        self.tolerance = tolerance
        self.coordinates = np.array([[p.x, p.y] for p in sample_points], dtype=np.float64).reshape(-1, 2)

    def deviations(self, axis: SymmetryAxis2D) -> np.ndarray:
        distances, _ = self.spatial_index.nearest_batch(axis.reflect_coordinates(self.coordinates))
        return distances

    def evaluate(self, axis: SymmetryAxis2D) -> SymmetryErrorProfile:
        """Compute full error metrics for the given axis."""
        n = len(self.sample_points)
        if n == 0:
            return SymmetryErrorProfile(
                axis=axis, sample_count=0, mean_deviation=0.0, rms_deviation=0.0,
                median_deviation=0.0, max_deviation=0.0, p90_deviation=0.0,
                hausdorff_distance=0.0, matched_ratio=0.0, loop_area_error_ratio=0.0,
                symmetry_score=0.0, confidence=0.0
            )

        devs = self.deviations(axis)
        matched_count = int(np.count_nonzero(devs <= self.tolerance))
        mean_dev = float(np.mean(devs))
        rms_dev = float(np.sqrt(np.mean(devs ** 2)))
        median_dev = float(np.median(devs))
        max_dev = float(np.max(devs))
        p90_dev = float(np.percentile(devs, 90))
        hausdorff = max_dev
        matched_ratio = matched_count / n

        # Loop area matching evaluation
        loop_area_error = self._evaluate_loop_symmetry(axis)

        # Composite Symmetry Score (0 to 100)
        # Score decreases exponentially with RMS deviation and is penalized by unmatched ratio
        decay_constant = max(0.5, self.tolerance * 5.0)  # e.g. 1.0 mm
        base_score = 100.0 * math.exp(-rms_dev / decay_constant)
        # Weight by matched ratio and loop consistency
        composite_score = base_score * (0.7 + 0.3 * matched_ratio) * (1.0 - 0.2 * min(1.0, loop_area_error))
        composite_score = max(0.0, min(100.0, composite_score))

        # Confidence metric (0.0 to 1.0)
        confidence = (composite_score / 100.0) * (0.5 + 0.5 * matched_ratio)
        confidence = max(0.0, min(1.0, confidence))

        return SymmetryErrorProfile(
            axis=axis,
            sample_count=n,
            mean_deviation=mean_dev,
            rms_deviation=rms_dev,
            median_deviation=median_dev,
            max_deviation=max_dev,
            p90_deviation=p90_dev,
            hausdorff_distance=hausdorff,
            matched_ratio=matched_ratio,
            loop_area_error_ratio=loop_area_error,
            symmetry_score=composite_score,
            confidence=confidence
        )

    def _evaluate_loop_symmetry(self, axis: SymmetryAxis2D) -> float:
        """Calculate relative area discrepancies between mirrored loops."""
        if len(self.loops) <= 1:
            return 0.0

        # Discard the largest loop (outer frame) for interior motif analysis
        motif_loops = self.loops[1:] if len(self.loops) > 1 else self.loops
        if not motif_loops:
            return 0.0

        centroids = [l.centroid for l in motif_loops]
        tree = PointSpatialIndex(centroids)
        total_rel_error = 0.0
        comparisons = 0

        for loop in motif_loops:
            refl_c = axis.reflect_point(loop.centroid)
            nearest_c, dist, idx = tree.nearest(refl_c)
            if nearest_c is not None and idx != -1:
                counterpart_loop = motif_loops[idx]
                a1 = loop.area
                a2 = counterpart_loop.area
                denom = max(a1, a2)
                if denom > 1e-4:
                    rel_err = abs(a1 - a2) / denom
                    total_rel_error += rel_err
                    comparisons += 1

        if comparisons == 0:
            return 0.0
        return total_rel_error / comparisons
