"""
Design Intent Detector.
Infers canonical geometric intentions: dominant angles, nominal kerf spacings,
collinear line bundles, and repeated motif structures from noisy geometry.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.features.extractor import LineFeature, LoopFeature, OrientationClass
from src.intent.constraints import (
    GeometricConstraint,
    CollinearConstraint,
    ParallelConstraint,
    EqualSpacingConstraint,
    EqualDimensionConstraint,
    ConstraintType,
    ConstraintStrictness
)


@dataclass
class AngleCluster:
    """A cluster of line segments sharing an intended canonical angle."""
    canonical_angle_deg: float
    line_indices: List[int]
    observed_angles: List[float]
    mean_angle: float
    std_angle: float
    confidence: float


@dataclass
class SpacingCluster:
    """A cluster of parallel gaps sharing an intended nominal spacing/kerf."""
    nominal_spacing_mm: float
    observed_spacings: List[float]
    median_spacing_mm: float
    mad_mm: float  # Median Absolute Deviation
    confidence: float
    line_pairs: List[Tuple[int, int]]


@dataclass
class DesignIntentReport:
    """Comprehensive report of inferred design intent."""
    dominant_angles: List[AngleCluster]
    nominal_spacings: List[SpacingCluster]
    collinear_bundles: List[List[int]]
    repeated_corner_motifs_found: bool
    corner_motif_indices: List[int]
    recommended_corner_size: Tuple[float, float]
    constraints: List[GeometricConstraint] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dominant_angles": [
                {
                    "canonical_deg": round(ac.canonical_angle_deg, 1),
                    "count": len(ac.line_indices),
                    "mean_deg": round(ac.mean_angle, 2),
                    "std_deg": round(ac.std_angle, 3),
                    "confidence": round(ac.confidence, 3)
                } for ac in self.dominant_angles
            ],
            "nominal_spacings_mm": [
                {
                    "nominal_mm": round(sc.nominal_spacing_mm, 2),
                    "count": len(sc.observed_spacings),
                    "median_mm": round(sc.median_spacing_mm, 2),
                    "mad_mm": round(sc.mad_mm, 3),
                    "confidence": round(sc.confidence, 3)
                } for sc in self.nominal_spacings
            ],
            "repeated_corner_motifs": self.repeated_corner_motifs_found,
            "recommended_corner_size_mm": [round(x, 2) for x in self.recommended_corner_size],
            "total_constraints": len(self.constraints)
        }


class DesignIntentDetector:
    """
    Infers design intent using robust statistics, kernel binning, and spatial proximity.
    """

    def __init__(self, angle_bin_deg: float = 6.0, spacing_bin_mm: float = 1.5):
        self.angle_bin_deg = angle_bin_deg
        self.spacing_bin_mm = spacing_bin_mm

    def detect_intent(
        self,
        lines: List[LineFeature],
        loops: List[LoopFeature],
        panel_bbox: BoundingBox2D
    ) -> DesignIntentReport:
        # 1. Detect Dominant Angle Clusters
        angle_clusters = self._detect_angle_clusters(lines)

        # 2. Detect Nominal Channel/Kerf Spacings
        spacing_clusters = self._detect_spacing_clusters(lines)

        # 3. Detect Collinear Bundles
        collinear_bundles = self._detect_collinear_bundles(lines)

        # 4. Detect Repeated Corner Motifs
        corner_indices, rec_size = self._detect_corner_motifs(loops, panel_bbox)
        has_corners = len(corner_indices) == 4

        # 5. Build Constraints List
        constraints: List[GeometricConstraint] = []

        # Angle constraints
        for ac in angle_clusters:
            if ac.confidence >= 0.75:
                constraints.append(ParallelConstraint(
                    constraint_id=f"parallel_deg_{int(ac.canonical_angle_deg)}",
                    constraint_type=ConstraintType.PARALLEL,
                    strictness=ConstraintStrictness.FIXED if ac.confidence > 0.9 else ConstraintStrictness.SOFT,
                    feature_ids=[f"line_{idx}" for idx in ac.line_indices],
                    target_angle_deg=ac.canonical_angle_deg,
                    description=f"Align {len(ac.line_indices)} lines to canonical {ac.canonical_angle_deg} deg"
                ))

        # Spacing constraints
        for sc in spacing_clusters:
            if sc.confidence >= 0.70:
                constraints.append(EqualSpacingConstraint(
                    constraint_id=f"spacing_{round(sc.nominal_spacing_mm, 1)}mm",
                    constraint_type=ConstraintType.EQUAL_SPACING,
                    strictness=ConstraintStrictness.SOFT,
                    pair_feature_ids=[(f"line_{i}", f"line_{j}") for i, j in sc.line_pairs],
                    target_spacing_mm=sc.nominal_spacing_mm,
                    description=f"Standardize {len(sc.line_pairs)} channel gaps to {sc.nominal_spacing_mm:.1f} mm"
                ))

        # Corner dimension constraint
        if has_corners:
            constraints.append(EqualDimensionConstraint(
                constraint_id="equal_corners",
                constraint_type=ConstraintType.EQUAL_DIMENSION,
                strictness=ConstraintStrictness.FIXED,
                motif_ids=[f"loop_{i}" for i in corner_indices],
                target_width=rec_size[0],
                target_height=rec_size[1],
                description=f"Equalize 4 corner boxes to {rec_size[0]:.2f} x {rec_size[1]:.2f} mm"
            ))

        return DesignIntentReport(
            dominant_angles=angle_clusters,
            nominal_spacings=spacing_clusters,
            collinear_bundles=collinear_bundles,
            repeated_corner_motifs_found=has_corners,
            corner_motif_indices=corner_indices,
            recommended_corner_size=rec_size,
            constraints=constraints
        )

    def _detect_angle_clusters(self, lines: List[LineFeature]) -> List[AngleCluster]:
        """Group line angles into canonical targets: 0, 45, 90, 135 deg or custom modes."""
        standard_targets = [0.0, 45.0, 90.0, 135.0]
        clusters: Dict[float, List[Tuple[int, float]]] = {t: [] for t in standard_targets}

        for i, line in enumerate(lines):
            ang = line.angle_deg
            # Check proximity to standard targets (with 180 wrapping for 0 deg)
            best_t = None
            min_d = float("inf")
            for t in standard_targets:
                d = abs(ang - t)
                if t == 0.0:
                    d = min(d, abs(ang - 180.0))
                if d < min_d:
                    min_d = d
                    best_t = t

            if min_d <= self.angle_bin_deg and best_t is not None:
                # Wrap near-180 angles to near-0
                raw_ang = ang if (best_t != 0.0 or ang <= 90.0) else (ang - 180.0)
                clusters[best_t].append((i, raw_ang))

        result: List[AngleCluster] = []
        total_lines = len(lines) if lines else 1

        for t in standard_targets:
            entries = clusters[t]
            if not entries:
                continue
            indices = [e[0] for e in entries]
            angles = [e[1] for e in entries]
            mean_a = float(np.mean(angles))
            std_a = float(np.std(angles))
            # Confidence based on proportion of lines and tight standard deviation
            tightness = max(0.0, 1.0 - (std_a / self.angle_bin_deg))
            coverage = min(1.0, len(indices) / (total_lines * 0.15))
            conf = 0.5 * tightness + 0.5 * coverage

            result.append(AngleCluster(
                canonical_angle_deg=t,
                line_indices=indices,
                observed_angles=angles,
                mean_angle=mean_a,
                std_angle=std_a,
                confidence=conf
            ))

        return result

    def _detect_spacing_clusters(self, lines: List[LineFeature]) -> List[SpacingCluster]:
        """Detect repeated channel / kerf / bridge widths between parallel segments."""
        spacings: List[Tuple[float, int, int]] = []

        # Find parallel line pairs within proximity (distance <= 40 mm)
        n = len(lines)
        for i in range(n):
            l1 = lines[i]
            for j in range(i + 1, n):
                l2 = lines[j]
                # Check near-parallel
                ang_diff = abs(l1.angle_deg - l2.angle_deg)
                if ang_diff > 90.0:
                    ang_diff = 180.0 - ang_diff
                if ang_diff > 3.0:
                    continue

                # Measure perpendicular distance
                # Project midpoint of l1 onto l2 line
                v2 = (l2.end - l2.start).normalized()
                if v2.length < 1e-6:
                    continue
                v_to_mid = l1.midpoint - l2.start
                perp_dist = abs(v_to_mid.cross(v2))

                # If reasonably close and have overlapping span
                if 4.0 <= perp_dist <= 35.0:
                    # Check projection overlap
                    proj1 = v_to_mid.dot(v2)
                    proj2 = (l1.end - l2.start).dot(v2)
                    l2_len = l2.length
                    if max(0, min(proj1, proj2)) <= min(l2_len, max(proj1, proj2)):
                        spacings.append((perp_dist, i, j))

        if not spacings:
            return []

        # Cluster spacings using robust binning
        vals = np.array([s[0] for s in spacings])
        clusters: List[SpacingCluster] = []

        # Find prominent peaks in histogram
        hist, bin_edges = np.histogram(vals, bins=max(5, int(35.0 / self.spacing_bin_mm)))
        for k in range(len(hist)):
            if hist[k] >= 3:  # At least 3 pairs share this spacing
                bin_min, bin_max = bin_edges[k], bin_edges[k + 1]
                pair_subset = [s for s in spacings if bin_min <= s[0] <= bin_max]
                c_vals = [s[0] for s in pair_subset]
                pairs = [(s[1], s[2]) for s in pair_subset]

                med = float(np.median(c_vals))
                mad = float(np.median(np.abs(np.array(c_vals) - med)))
                conf = min(1.0, len(c_vals) / 8.0) * max(0.0, 1.0 - (mad / 2.0))

                clusters.append(SpacingCluster(
                    nominal_spacing_mm=round(med, 2),
                    observed_spacings=c_vals,
                    median_spacing_mm=med,
                    mad_mm=mad,
                    confidence=conf,
                    line_pairs=pairs
                ))

        # Sort clusters by frequency
        clusters.sort(key=lambda c: len(c.observed_spacings), reverse=True)
        return clusters[:4]

    def _detect_collinear_bundles(self, lines: List[LineFeature]) -> List[List[int]]:
        """Identify groups of collinear segments."""
        bundles: List[List[int]] = []
        used = set()

        for i, l1 in enumerate(lines):
            if i in used:
                continue
            current_bundle = [i]
            v1 = (l1.end - l1.start).normalized()
            if v1.length < 1e-6:
                continue

            for j in range(i + 1, len(lines)):
                if j in used:
                    continue
                l2 = lines[j]
                # Angle check
                ang_diff = abs(l1.angle_deg - l2.angle_deg)
                if ang_diff > 90.0:
                    ang_diff = 180.0 - ang_diff
                if ang_diff > 2.0:
                    continue

                # Collinear distance check (distance of l2 endpoints to l1 line)
                d1 = abs((l2.start - l1.start).cross(v1))
                d2 = abs((l2.end - l1.start).cross(v1))
                if d1 < 0.5 and d2 < 0.5:
                    current_bundle.append(j)

            if len(current_bundle) >= 2:
                for idx in current_bundle:
                    used.add(idx)
                bundles.append(current_bundle)

        return bundles

    def _detect_corner_motifs(
        self,
        loops: List[LoopFeature],
        panel_bbox: BoundingBox2D
    ) -> Tuple[List[int], Tuple[float, float]]:
        """Identify 4-corner motif boxes and calculate recommended canonical dimensions."""
        corners: List[Tuple[int, LoopFeature]] = []
        cx = (panel_bbox.min_x + panel_bbox.max_x) * 0.5
        cy = (panel_bbox.min_y + panel_bbox.max_y) * 0.5

        for i, loop in enumerate(loops):
            if loop.loop_category == "CORNER_BOX" or (
                loop.vertex_count == 4 and
                abs(loop.centroid.x - cx) > panel_bbox.width * 0.25 and
                abs(loop.centroid.y - cy) > panel_bbox.height * 0.25
            ):
                corners.append((i, loop))

        if len(corners) == 4:
            widths = [c[1].width for c in corners]
            heights = [c[1].height for c in corners]
            # Use median to resist single stretched/compressed outliers
            rec_w = float(np.median(widths))
            rec_h = float(np.median(heights))
            return [c[0] for c in corners], (rec_w, rec_h)

        return [], (0.0, 0.0)
