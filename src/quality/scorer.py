"""
Visual Quality & Regularity Scorer.
Evaluates holistic quality: Symmetry + Spacing + Alignment + Angle + Proportion - Deformation.
Enforces the core principle: "100% symmetric but warped = FAILED REPAIR".
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
import numpy as np

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.io.dxf_io import CADModel2D
from src.features.extractor import FeatureExtractor, LineFeature, LoopFeature
from src.intent.detector import DesignIntentDetector, DesignIntentReport
from src.regularization.deformation_detector import DeformationDetector, DeformationReport
from src.symmetry.scorer import SymmetryAnalyzer, SymmetryAnalysisResult


@dataclass
class VisualQualityScore:
    """Holistic visual quality and geometric regularity score (0 - 100)."""
    symmetry_score: float         # 0.0 - 100.0
    spacing_score: float          # 0.0 - 100.0 (consistency of channel widths)
    alignment_score: float        # 0.0 - 100.0 (collinearity of continuous edges)
    angle_score: float            # 0.0 - 100.0 (regularity of canonical orientations)
    proportion_score: float       # 0.0 - 100.0 (uniformity of corresponding motif dimensions)
    deformation_penalty: float    # 0.0 (no kinks) to 100.0 (severely warped)
    composite_quality: float      # 0.0 - 100.0 (holistic visual beauty index)
    confidence: float             # 0.0 - 1.0
    verdict: str                  # AUTO_ACCEPT, REVIEW, REJECT

    def to_dict(self) -> Dict[str, Any]:
        return {
            "composite_visual_quality": round(self.composite_quality, 2),
            "symmetry_score": round(self.symmetry_score, 2),
            "spacing_consistency": round(self.spacing_score, 2),
            "alignment_collinearity": round(self.alignment_score, 2),
            "angle_regularity": round(self.angle_score, 2),
            "motif_proportion": round(self.proportion_score, 2),
            "deformation_penalty": round(self.deformation_penalty, 2),
            "confidence": round(self.confidence, 3),
            "verdict": self.verdict
        }


class VisualQualityScorer:
    """
    Evaluates visual quality and regularity metrics for CAD models.
    """

    def __init__(
        self,
        weight_symmetry: float = 0.25,
        weight_spacing: float = 0.20,
        weight_angle: float = 0.20,
        weight_proportion: float = 0.20,
        weight_alignment: float = 0.15
    ):
        self.w_symm = weight_symmetry
        self.w_space = weight_spacing
        self.w_ang = weight_angle
        self.w_prop = weight_proportion
        self.w_align = weight_alignment

    def score(
        self,
        model: CADModel2D,
        symm_result: Optional[SymmetryAnalysisResult] = None,
        intent_report: Optional[DesignIntentReport] = None
    ) -> VisualQualityScore:
        # 1. Symmetry Score
        if symm_result is None:
            analyzer = SymmetryAnalyzer()
            symm_result = analyzer.analyze(model)
        s_symm = symm_result.primary_profile.symmetry_score

        # 2. Features & Intent
        fe = FeatureExtractor()
        features = fe.extract(model)
        lines: List[LineFeature] = features["lines"]
        loops: List[LoopFeature] = features["loops"]

        if intent_report is None:
            detector = DesignIntentDetector()
            intent_report = detector.detect_intent(lines, loops, model.bbox)

        # 3. Angle Regularity Score
        # How close are lines to their canonical target angles
        if lines:
            devs = [l.angle_deviation_deg for l in lines]
            mean_dev = float(np.mean(devs))
            s_angle = max(0.0, min(100.0, 100.0 - (mean_dev * 18.0)))
        else:
            s_angle = 100.0

        # 4. Spacing Consistency Score
        # Evaluate standard deviation of spacings in dominant spacing clusters
        if intent_report.nominal_spacings:
            mads = [sc.mad_mm for sc in intent_report.nominal_spacings]
            avg_mad = float(np.mean(mads))
            s_spacing = max(0.0, min(100.0, 100.0 - (avg_mad * 35.0)))
        else:
            s_spacing = 85.0

        # 5. Motif Proportion Score
        # Check equality of dimensions across the 4 corner loops
        corner_loops = [l for l in loops if l.loop_category == "CORNER_BOX"]
        if len(corner_loops) >= 2:
            areas = [l.area for l in corner_loops if l.area > 1e-4]
            if areas:
                ratio = min(areas) / max(areas)
                s_prop = max(0.0, min(100.0, ratio * 100.0))
            else:
                s_prop = 100.0
        else:
            s_prop = 90.0

        # 6. Alignment & Collinearity Score
        if intent_report.collinear_bundles:
            total_bundled = sum(len(b) for b in intent_report.collinear_bundles)
            s_align = min(100.0, 70.0 + (total_bundled / len(lines) * 30.0)) if lines else 100.0
        else:
            s_align = 80.0

        # 7. Deformation & Kink Penalty
        def_detector = DeformationDetector()
        def_report = def_detector.analyze(model)
        def_penalty = def_report.deformation_score

        # 8. Composite Visual Quality
        composite = (
            self.w_symm * s_symm +
            self.w_space * s_spacing +
            self.w_ang * s_angle +
            self.w_prop * s_prop +
            self.w_align * s_align
        ) - (def_penalty * 0.45)

        composite = max(0.0, min(100.0, composite))

        # 9. Confidence and Decision Verdict
        conf = min(1.0, (s_symm / 100.0 * 0.4 + s_angle / 100.0 * 0.3 + s_prop / 100.0 * 0.3))

        if composite >= 85.0 and s_symm >= 90.0 and def_penalty < 15.0:
            verdict = "AUTO_ACCEPT"
        elif composite >= 60.0:
            verdict = "REVIEW"
        else:
            verdict = "REJECT"

        return VisualQualityScore(
            symmetry_score=s_symm,
            spacing_score=s_spacing,
            alignment_score=s_align,
            angle_score=s_angle,
            proportion_score=s_prop,
            deformation_penalty=def_penalty,
            composite_quality=composite,
            confidence=conf,
            verdict=verdict
        )
