"""
Multi-Hypothesis Repair Candidate Generator.
Generates multiple competing repair candidates:
  - Candidate A: Canonical Design Intent Reconstruction (Canonical corners + regularized kerfs)
  - Candidate B: 4-Quadrant Regularized
  - Candidate C: Bilateral L->R Regularized
  - Candidate D: Minimum Necessary Modification
Ranks them using composite objective function and minimum change principle.
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.io.dxf_io import CADModel2D
from src.features.extractor import FeatureExtractor, LineFeature, LoopFeature
from src.intent.detector import DesignIntentDetector, DesignIntentReport
from src.regularization.angle_regularizer import AngleRegularizer
from src.regularization.canonical_motif import CanonicalMotifReconstructor
from src.quality.scorer import VisualQualityScorer, VisualQualityScore
from src.validation.validator import ModelValidator, ModelValidationResult
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder


@dataclass
class RepairCandidate:
    """A competing repair hypothesis with metrics and visual quality evaluation."""
    candidate_id: str
    strategy_name: str
    repaired_model: CADModel2D
    quality_score: VisualQualityScore
    validation: ModelValidationResult
    change_ratio_percent: float
    objective_cost: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "strategy": self.strategy_name,
            "description": self.description,
            "visual_quality": self.quality_score.composite_quality,
            "symmetry_score": self.quality_score.symmetry_score,
            "angle_regularity": self.quality_score.angle_score,
            "spacing_consistency": self.quality_score.spacing_score,
            "deformation_penalty": self.quality_score.deformation_penalty,
            "change_ratio_percent": round(self.change_ratio_percent, 2),
            "is_valid": self.validation.is_valid,
            "validation": self.validation.to_dict(),
            "objective_cost": round(self.objective_cost, 2),
            "verdict": self.quality_score.verdict
        }


class CandidateRepairGenerator:
    """
    Generates and evaluates multiple candidate repair hypotheses.
    """

    def __init__(self, kerf_tolerance_mm: float = 0.5, straighten_boundary: bool = True):
        self.kerf_tolerance = kerf_tolerance_mm
        self.quality_scorer = VisualQualityScorer()
        self.validator = ModelValidator()
        self.angle_regularizer = AngleRegularizer(snap_tolerance_deg=4.0)
        self.straighten_boundary = straighten_boundary

    def generate_all(
        self,
        model: CADModel2D,
        features: Optional[Dict[str, Any]] = None,
        intent: Optional[DesignIntentReport] = None,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> List[RepairCandidate]:
        return self.generate_all_candidates(model, features=features, intent=intent, exclusion_zones=exclusion_zones)

    def generate_all_candidates(
        self,
        model: CADModel2D,
        features: Optional[Dict[str, Any]] = None,
        intent: Optional[DesignIntentReport] = None,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> List[RepairCandidate]:
        self._quadrant_base = None
        if features is None:
            fe = FeatureExtractor()
            features = fe.extract(model)

        lines: List[LineFeature] = features["lines"]
        loops: List[LoopFeature] = features["loops"]

        if intent is None:
            detector = DesignIntentDetector()
            intent = detector.detect_intent(lines, loops, model.bbox)

        candidates: List[RepairCandidate] = []

        # Candidate A: Canonical Design Intent Reconstruction (Equal corners, regularized kerfs)
        c_a = self._generate_canonical_intent(model, loops, intent, exclusion_zones=exclusion_zones)
        candidates.append(c_a)

        # Candidate B: 4-Quadrant Regularized
        c_b = self._generate_4_quadrant_regularized(model, loops, intent, exclusion_zones=exclusion_zones)
        candidates.append(c_b)

        # Candidate C: Bilateral L->R Regularized
        c_c = self._generate_bilateral_regularized(model, loops, intent, exclusion_zones=exclusion_zones)
        candidates.append(c_c)

        # Candidate D: Minimum Necessary Change
        c_d = self._generate_minimum_change(model, intent, exclusion_zones=exclusion_zones)
        candidates.append(c_d)

        # Never recommend invalid geometry just because its quality score is high.
        for candidate in candidates:
            if not candidate.repaired_model.lines:
                candidate.validation.is_valid = False
                candidate.validation.validation_errors.append("Phương án không chứa nét cắt.")
            if model.arcs and len(candidate.repaired_model.arcs) != len(model.arcs):
                candidate.validation.is_valid = False
                candidate.validation.validation_errors.append("Phương án làm mất cung tròn của bản gốc.")
        candidates.sort(key=lambda c: (not c.validation.is_valid, c.objective_cost, c.candidate_id))
        return candidates

    def _get_quadrant_base(self, model):
        from src.repair.engine import PatternRepairEngine
        if self._quadrant_base is None:
            self._quadrant_base = PatternRepairEngine().repair(
                model, strategy="4_quadrant", straighten_boundary=self.straighten_boundary)
        return self._quadrant_base

    def _apply_healing_and_exclusions(
        self,
        lines: List[LineSegment2D],
        arcs: List[Arc2D],
        original_model: CADModel2D,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> Tuple[List[LineSegment2D], List[Arc2D]]:
        from src.topology.healing import TopologyHealer
        if exclusion_zones:
            kept_lines = []
            for l in lines:
                in_ex = any(ez.contains_point(l.start) or ez.contains_point(l.end) for ez in exclusion_zones)
                if not in_ex:
                    kept_lines.append(l)
            kept_arcs = []
            for a in arcs:
                in_ex = any(ez.contains_point(a.start_point) or ez.contains_point(a.end_point) for ez in exclusion_zones)
                if not in_ex:
                    kept_arcs.append(a)
            for ol in original_model.lines:
                if any(ez.contains_point(ol.start) or ez.contains_point(ol.end) for ez in exclusion_zones):
                    kept_lines.append(ol)
            for oa in original_model.arcs:
                if any(ez.contains_point(oa.start_point) or ez.contains_point(oa.end_point) for ez in exclusion_zones):
                    kept_arcs.append(oa)
            lines = kept_lines
            arcs = kept_arcs

        healer = TopologyHealer(snap_radius_mm=0.05, preserve_tabs=True)
        healed_lines, healed_arcs, _ = healer.heal_and_stitch(lines, arcs)
        return healed_lines, healed_arcs

    def _generate_canonical_intent(
        self,
        model: CADModel2D,
        loops: List[LoopFeature],
        intent: DesignIntentReport,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> RepairCandidate:
        base_res = self._get_quadrant_base(model)

        # Regularize all loops while preserving exact vertex closure
        graph = TopologyGraph.from_cad_model(base_res.repaired_model)
        cycle_loops = CycleFinder(graph).extract_loops()
        reg_loops = [self.angle_regularizer.regularize_loop(l.points) for l in cycle_loops]

        # Equalize 4 corner boxes if present
        bbox = model.bbox
        cx = (bbox.min_x + bbox.max_x) * 0.5
        cy = (bbox.min_y + bbox.max_y) * 0.5

        if intent.repeated_corner_motifs_found:
            rec_w, rec_h = intent.recommended_corner_size
            for idx, l_pts in enumerate(reg_loops):
                if len(l_pts) == 4:
                    xs = [p.x for p in l_pts]
                    ys = [p.y for p in l_pts]
                    c_x = float(np.mean(xs))
                    c_y = float(np.mean(ys))
                    # If this is a corner box
                    if abs(c_x - cx) > bbox.width * 0.25 and abs(c_y - cy) > bbox.height * 0.25:
                        sign_x = 1.0 if c_x > cx else -1.0
                        sign_y = 1.0 if c_y > cy else -1.0
                        # Dynamically measure margin from outer frame
                        margins_x = []
                        margins_y = []
                        for lp in reg_loops:
                            if len(lp) == 4:
                                lxs = [p.x for p in lp]
                                lys = [p.y for p in lp]
                                lcx = float(np.mean(lxs))
                                lcy = float(np.mean(lys))
                                if abs(lcx - cx) > bbox.width * 0.25 and abs(lcy - cy) > bbox.height * 0.25:
                                    mx = (min(lxs) - bbox.min_x) if lcx < cx else (bbox.max_x - max(lxs))
                                    my = (min(lys) - bbox.min_y) if lcy < cy else (bbox.max_y - max(lys))
                                    if mx > 0: margins_x.append(mx)
                                    if my > 0: margins_y.append(my)

                        margin_x = float(np.median(margins_x)) if margins_x else 18.5
                        margin_y = float(np.median(margins_y)) if margins_y else 18.5
                        if sign_x < 0:
                            x1 = bbox.min_x + margin_x
                            x2 = x1 + rec_w
                        else:
                            x2 = bbox.max_x - margin_x
                            x1 = x2 - rec_w

                        if sign_y < 0:
                            y1 = bbox.min_y + margin_y
                            y2 = y1 + rec_h
                        else:
                            y2 = bbox.max_y - margin_y
                            y1 = y2 - rec_h

                        reg_loops[idx] = [Point2D(x1, y1), Point2D(x2, y1), Point2D(x2, y2), Point2D(x1, y2)]

        lines = self._loops_to_lines(reg_loops, original_model=model)
        arcs = list(model.arcs)
        lines, arcs = self._apply_healing_and_exclusions(lines, arcs, model, exclusion_zones)

        rep_model = CADModel2D(
            lines=lines,
            arcs=arcs,
            circles=model.circles,
            layers=model.layers,
            source_file=model.source_file,
            units="mm",
            metadata={"strategy": "canonical_intent"}
        )

        q = self.quality_scorer.score(rep_model)
        val = self.validator.validate(rep_model, model)
        ch_ratio = self._compute_change_ratio(model, rep_model)

        cost = (100.0 - q.composite_quality) + (0.15 * ch_ratio) + (0.0 if val.is_valid else 100.0)

        return RepairCandidate(
            candidate_id="candidate_a",
            strategy_name="CANONICAL_INTENT",
            repaired_model=rep_model,
            quality_score=q,
            validation=val,
            change_ratio_percent=ch_ratio,
            objective_cost=cost,
            description="Tái tạo Quy Chuẩn (Canonical): Đồng bộ 4 góc vuông bằng nhau, căn chỉnh lại khoảng cách khe cắt, triệt tiêu hoàn toàn móp méo."
        )

    def _generate_4_quadrant_regularized(
        self,
        model: CADModel2D,
        loops: List[LoopFeature],
        intent: DesignIntentReport,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> RepairCandidate:
        res = self._get_quadrant_base(model)

        graph = TopologyGraph.from_cad_model(res.repaired_model)
        cycle_loops = CycleFinder(graph).extract_loops()
        reg_loops = [self.angle_regularizer.regularize_loop(l.points) for l in cycle_loops]

        lines = self._loops_to_lines(reg_loops, original_model=model)
        arcs = list(model.arcs)
        lines, arcs = self._apply_healing_and_exclusions(lines, arcs, model, exclusion_zones)

        rep_model = CADModel2D(
            lines=lines,
            arcs=arcs,
            circles=model.circles,
            layers=model.layers,
            source_file=model.source_file,
            units="mm",
            metadata={"strategy": "4_quadrant_regularized"}
        )

        q = self.quality_scorer.score(rep_model)
        val = self.validator.validate(rep_model, model)
        ch_ratio = self._compute_change_ratio(model, rep_model)
        cost = (100.0 - q.composite_quality) + (0.15 * ch_ratio) + (0.0 if val.is_valid else 100.0)

        return RepairCandidate(
            candidate_id="candidate_b",
            strategy_name="4_QUADRANT_REGULARIZED",
            repaired_model=rep_model,
            quality_score=q,
            validation=val,
            change_ratio_percent=ch_ratio,
            objective_cost=cost,
            description="Đối Xứng 4 Góc Quy Chuẩn Hóa: Nhân bản 1/4 góc sang 4 góc kết hợp nắn thẳng góc xiên."
        )

    def _generate_bilateral_regularized(
        self,
        model: CADModel2D,
        loops: List[LoopFeature],
        intent: DesignIntentReport,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> RepairCandidate:
        from src.repair.engine import PatternRepairEngine
        engine = PatternRepairEngine()
        res = engine.repair(model, strategy="mirror_left_to_right", straighten_boundary=self.straighten_boundary)

        graph = TopologyGraph.from_cad_model(res.repaired_model)
        cycle_loops = CycleFinder(graph).extract_loops()
        reg_loops = [self.angle_regularizer.regularize_loop(l.points) for l in cycle_loops]

        lines = self._loops_to_lines(reg_loops, original_model=model)
        arcs = list(model.arcs)
        lines, arcs = self._apply_healing_and_exclusions(lines, arcs, model, exclusion_zones)

        rep_model = CADModel2D(
            lines=lines,
            arcs=arcs,
            circles=model.circles,
            layers=model.layers,
            source_file=model.source_file,
            units="mm",
            metadata={"strategy": "bilateral_l2r"}
        )

        q = self.quality_scorer.score(rep_model)
        val = self.validator.validate(rep_model, model)
        ch_ratio = self._compute_change_ratio(model, rep_model)
        cost = (100.0 - q.composite_quality) + (0.15 * ch_ratio) + (0.0 if val.is_valid else 100.0)

        return RepairCandidate(
            candidate_id="candidate_c",
            strategy_name="BILATERAL_L2R",
            repaired_model=rep_model,
            quality_score=q,
            validation=val,
            change_ratio_percent=ch_ratio,
            objective_cost=cost,
            description="Mirror Trái sang Phải: Giữ nguyên nửa bên trái chuẩn, lật sang phải và nắn góc thẳng."
        )

    def _generate_minimum_change(
        self,
        model: CADModel2D,
        intent: DesignIntentReport,
        exclusion_zones: Optional[List[BoundingBox2D]] = None
    ) -> RepairCandidate:
        graph = TopologyGraph.from_cad_model(model)
        cycle_loops = CycleFinder(graph).extract_loops()
        if cycle_loops:
            reg_loops = [self.angle_regularizer.regularize_loop(l.points) for l in cycle_loops]
            lines = self._loops_to_lines(reg_loops, original_model=model)
        else:
            raw_lines, _ = self.angle_regularizer.regularize_lines(model.lines)
            lines = self._deduplicate_lines(raw_lines)

        arcs = list(model.arcs)
        lines, arcs = self._apply_healing_and_exclusions(lines, arcs, model, exclusion_zones)

        rep_model = CADModel2D(
            lines=lines,
            arcs=arcs,
            circles=model.circles,
            layers=model.layers,
            source_file=model.source_file,
            units="mm",
            metadata={"strategy": "minimum_change"}
        )

        q = self.quality_scorer.score(rep_model)
        val = self.validator.validate(rep_model, model)
        ch_ratio = self._compute_change_ratio(model, rep_model)
        cost = (100.0 - q.composite_quality) + (0.15 * ch_ratio) + (0.0 if val.is_valid else 100.0)

        return RepairCandidate(
            candidate_id="candidate_d",
            strategy_name="MINIMUM_CHANGE",
            repaired_model=rep_model,
            quality_score=q,
            validation=val,
            change_ratio_percent=ch_ratio,
            objective_cost=cost,
            description="Can Thiệp Tối Thiểu (Minimum Change): Chỉ nắn góc các nét bị xiên nhẹ, giữ nguyên 100% bố cục."
        )

    def _loops_to_lines(self, loops: List[List[Point2D]], original_model: Optional[CADModel2D] = None) -> List[LineSegment2D]:
        lines: List[LineSegment2D] = []
        for loop in loops:
            n = len(loop)
            for i in range(n):
                p1 = loop[i]
                p2 = loop[(i + 1) % n]
                if p1.distance_to(p2) > 1e-4:
                    layer = "0"
                    if original_model and original_model.lines:
                        mid = Point2D((p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5)
                        closest = min(original_model.lines, key=lambda ol: ol.distance_to_point(mid))
                        layer = closest.layer
                    lines.append(LineSegment2D(p1, p2, layer=layer))
        return self._deduplicate_lines(lines)

    def _compute_change_ratio(self, original: CADModel2D, repaired: CADModel2D) -> float:
        if not original.lines or not repaired.lines:
            return 0.0 if not original.lines and not repaired.lines else 100.0
        n_orig = len(original.lines)
        n_rep = len(repaired.lines)
        count_diff = abs(n_orig - n_rep) / max(n_orig, 1)

        from src.spatial.index import PointSpatialIndex
        orig_pts = [l.midpoint for l in original.lines]
        rep_pts = [l.midpoint for l in repaired.lines]
        forward, _ = PointSpatialIndex(rep_pts).nearest_batch([[p.x, p.y] for p in orig_pts])
        backward, _ = PointSpatialIndex(orig_pts).nearest_batch([[p.x, p.y] for p in rep_pts])
        mean_shift = float((np.mean(forward) + np.mean(backward)) * 0.5)
        shift_ratio = min(1.0, mean_shift / 25.0)

        return min(100.0, (0.5 * count_diff + 0.5 * shift_ratio) * 100.0)

    def _deduplicate_lines(self, lines: List[LineSegment2D], tol: float = 0.05) -> List[LineSegment2D]:
        unique: List[LineSegment2D] = []
        for line in lines:
            is_dup = False
            for u in unique:
                if line.is_coincident(u, tol=tol):
                    is_dup = True
                    break
            if not is_dup:
                unique.append(line)
        return unique
