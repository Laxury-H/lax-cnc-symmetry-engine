"""
High-level Symmetry Analyzer and Scorer for CAD models.
Orchestrates topology extraction, axis discovery, multi-criteria scoring, and defect localization.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder, ClosedLoop
from src.symmetry.axis_finder import SymmetryAxisFinder
from src.symmetry.error_metrics import SymmetryEvaluator, SymmetryErrorProfile


@dataclass
class LoopSymmetryPair:
    """Pair of corresponding mirrored loops across symmetry axis."""
    loop_left: ClosedLoop
    loop_right: ClosedLoop
    centroid_deviation: float   # mm
    area_left: float            # mm²
    area_right: float           # mm²
    area_diff_ratio: float      # |A1 - A2| / max(A1, A2)


@dataclass
class SymmetryAnalysisResult:
    """Complete diagnostic report of CAD model symmetry."""
    primary_axis: SymmetryAxis2D
    primary_profile: SymmetryErrorProfile
    secondary_axis: Optional[SymmetryAxis2D] = None
    secondary_profile: Optional[SymmetryErrorProfile] = None
    total_entities: int = 0
    total_loops: int = 0
    outer_loop: Optional[ClosedLoop] = None
    motif_pairs: List[LoopSymmetryPair] = field(default_factory=list)
    unpaired_loops: List[ClosedLoop] = field(default_factory=list)
    classification: str = ""    # HIGH_SYMMETRY, DISTORTED_SYMMETRY, INTENDED_ASYMMETRIC
    recommended_action: str = "" # AUTO_REPAIR, REVIEW, REJECT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification,
            "recommended_action": self.recommended_action,
            "primary_axis": {
                "angle_deg": round(self.primary_axis.angle_degrees, 3),
                "origin": self.primary_axis.origin.to_dict(),
                "is_vertical": self.primary_axis.is_vertical,
                "is_horizontal": self.primary_axis.is_horizontal,
            },
            "primary_error_profile": self.primary_profile.to_dict(),
            "secondary_axis": {
                "angle_deg": round(self.secondary_axis.angle_degrees, 3),
                "origin": self.secondary_axis.origin.to_dict(),
            } if self.secondary_axis and self.secondary_profile else None,
            "total_entities": self.total_entities,
            "total_loops": self.total_loops,
            "paired_motifs_count": len(self.motif_pairs),
            "unpaired_motifs_count": len(self.unpaired_loops),
            "worst_motif_area_diff": round(max((p.area_diff_ratio for p in self.motif_pairs), default=0.0), 4),
            "worst_motif_centroid_dev_mm": round(max((p.centroid_deviation for p in self.motif_pairs), default=0.0), 3)
        }


class SymmetryAnalyzer:
    """Orchestrates comprehensive symmetry analysis for a CADModel2D."""

    def __init__(self, tolerance: float = 0.20, endpoint_tolerance: float = 0.10):
        self.tolerance = tolerance
        self.endpoint_tolerance = endpoint_tolerance
        self.axis_finder = SymmetryAxisFinder(tolerance=tolerance)

    def analyze(self, model: CADModel2D) -> SymmetryAnalysisResult:
        """Run full symmetry analysis pipeline on CADModel2D."""
        # 1. Build topology graph and extract closed loops
        graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=self.endpoint_tolerance)
        cycle_finder = CycleFinder(graph)
        loops = cycle_finder.extract_loops()

        # 2. Sample points for continuous metric evaluation
        sampled_points = model.get_all_sampled_points(num_samples_per_entity=12)

        # 3. Discover primary symmetry axis
        primary_axis, primary_profile = self.axis_finder.find_best_axis(
            points=sampled_points,
            loops=loops,
            search_diagonal=True
        )

        # 4. Check for orthogonal secondary symmetry axis
        secondary_res = self.axis_finder.find_orthogonal_secondary_axis(
            primary_axis=primary_axis,
            points=sampled_points,
            loops=loops
        )
        secondary_axis = secondary_res[0] if secondary_res else None
        secondary_profile = secondary_res[1] if secondary_res else None

        # 5. Classify loops: identify outer boundary vs internal motif pairs
        outer_loop = loops[0] if loops else None
        motif_loops = loops[1:] if len(loops) > 1 else []
        motif_pairs, unpaired = self._pair_mirrored_loops(primary_axis, motif_loops)

        # 6. Classify design intent and recommended action
        classification, action = self._classify_result(primary_profile, len(motif_pairs), len(unpaired))

        return SymmetryAnalysisResult(
            primary_axis=primary_axis,
            primary_profile=primary_profile,
            secondary_axis=secondary_axis,
            secondary_profile=secondary_profile,
            total_entities=model.total_entities,
            total_loops=len(loops),
            outer_loop=outer_loop,
            motif_pairs=motif_pairs,
            unpaired_loops=unpaired,
            classification=classification,
            recommended_action=action
        )

    def _pair_mirrored_loops(
        self,
        axis: SymmetryAxis2D,
        loops: List[ClosedLoop]
    ) -> Tuple[List[LoopSymmetryPair], List[ClosedLoop]]:
        """Pair up corresponding motifs across the symmetry axis."""
        pairs: List[LoopSymmetryPair] = []
        unpaired: List[ClosedLoop] = list(loops)

        used_indices = set()
        n = len(loops)

        for i in range(n):
            if i in used_indices:
                continue
            l1 = loops[i]
            refl_c1 = axis.reflect_point(l1.centroid)

            best_match_idx = -1
            min_dist = float("inf")

            for j in range(n):
                if j in used_indices or j == i:
                    continue
                l2 = loops[j]
                d = refl_c1.distance_to(l2.centroid)
                # Check area compatibility (within 35%)
                max_a = max(l1.area, l2.area)
                if max_a > 1e-4 and abs(l1.area - l2.area) / max_a < 0.35:
                    if d < min_dist:
                        min_dist = d
                        best_match_idx = j

            # Self-symmetric motif on the axis (e.g. central square)
            if best_match_idx == -1:
                # Check if loop is centered on the axis
                dist_to_axis = abs(axis.distance_to_point(l1.centroid))
                if dist_to_axis < 15.0:  # mm
                    # Loop lies on the axis
                    used_indices.add(i)
                    pairs.append(LoopSymmetryPair(
                        loop_left=l1,
                        loop_right=l1,
                        centroid_deviation=dist_to_axis,
                        area_left=l1.area,
                        area_right=l1.area,
                        area_diff_ratio=0.0
                    ))
                    continue

            if best_match_idx != -1 and min_dist < 30.0:  # reasonable proximity tolerance for distorted files
                used_indices.add(i)
                used_indices.add(best_match_idx)
                l2 = loops[best_match_idx]
                max_a = max(l1.area, l2.area)
                area_diff = abs(l1.area - l2.area) / max_a if max_a > 0 else 0.0

                pairs.append(LoopSymmetryPair(
                    loop_left=l1,
                    loop_right=l2,
                    centroid_deviation=min_dist,
                    area_left=l1.area,
                    area_right=l2.area,
                    area_diff_ratio=area_diff
                ))

        remaining = [loops[idx] for idx in range(n) if idx not in used_indices]
        return pairs, remaining

    def _classify_result(
        self,
        profile: SymmetryErrorProfile,
        num_paired_motifs: int,
        num_unpaired_motifs: int
    ) -> Tuple[str, str]:
        """Determine design classification and recommended repair action."""
        score = profile.symmetry_score
        rms = profile.rms_deviation
        matched = profile.matched_ratio

        if score >= 95.0 and rms <= 0.15 and matched >= 0.95:
            return "PERFECT_SYMMETRIC", "NO_REPAIR_NEEDED"

        # Check if intended symmetry is evident despite distortion
        if matched >= 0.70 or num_paired_motifs >= 3:
            if score >= 80.0 or (num_paired_motifs >= 5 and matched >= 0.65):
                return "DISTORTED_SYMMETRY", "AUTO_REPAIR" if score >= 85.0 else "REVIEW"
            else:
                return "SEVERELY_DISTORTED_SYMMETRY", "REVIEW"

        # If very few motifs match and score is low, likely intentional asymmetry
        if matched < 0.40 and num_paired_motifs <= 1:
            return "INTENDED_ASYMMETRIC", "REJECT"

        return "UNCERTAIN_ASYMMETRY", "REVIEW"
