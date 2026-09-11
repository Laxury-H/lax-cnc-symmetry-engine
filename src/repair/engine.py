"""
Phase 2 Repair Engine for CNC Patterns.
Provides deterministic geometric repair strategies:
  1. 4-Fold Quadrant Symmetry (1/4 quadrant reflected to all 4 corners)
  2. Mirror Left to Right (L -> R)
  3. Mirror Right to Left (R -> L)
  4. Mirror Bottom to Top (Bottom -> Top)
  5. Mirror Top to Bottom (Top -> Bottom)
  6. Canonical Consensus Reconstruction (Averaging corresponding motifs)
  7. Outer Boundary Straightening (True orthogonal rectangle)
  8. Topology Cleanup (Watertight loop verification, duplicate removal)
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder, ClosedLoop
from src.symmetry.scorer import SymmetryAnalyzer, SymmetryAnalysisResult


@dataclass
class RepairResult:
    """Summary of repair operations and before/after metrics."""
    repaired_model: CADModel2D
    strategy_used: str
    symmetry_score_before: float
    symmetry_score_after: float
    max_deviation_before: float
    max_deviation_after: float
    rms_deviation_before: float
    rms_deviation_after: float
    is_watertight: bool
    total_loops_repaired: int
    operations_log: List[str] = field(default_factory=list)
    visual_quality_before: Optional[float] = None
    visual_quality_after: Optional[float] = None
    spacing_score_before: Optional[float] = None
    spacing_score_after: Optional[float] = None
    alignment_score_before: Optional[float] = None
    alignment_score_after: Optional[float] = None
    angle_score_before: Optional[float] = None
    angle_score_after: Optional[float] = None
    deformation_before: Optional[float] = None
    deformation_after: Optional[float] = None
    verdict: str = "AUTO_ACCEPT"
    candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "strategy_used": self.strategy_used,
            "symmetry_score_before": round(self.symmetry_score_before, 2),
            "symmetry_score_after": round(self.symmetry_score_after, 2),
            "max_deviation_before_mm": round(self.max_deviation_before, 4),
            "max_deviation_after_mm": round(self.max_deviation_after, 4),
            "rms_deviation_before_mm": round(self.rms_deviation_before, 4),
            "rms_deviation_after_mm": round(self.rms_deviation_after, 4),
            "is_watertight": self.is_watertight,
            "total_loops": self.total_loops_repaired,
            "operations": self.operations_log
        }
        if self.visual_quality_after is not None:
            d["visual_quality_before"] = round(self.visual_quality_before, 2) if self.visual_quality_before is not None else None
            d["visual_quality_after"] = round(self.visual_quality_after, 2)
            d["spacing_score_after"] = round(self.spacing_score_after, 2) if self.spacing_score_after is not None else None
            d["alignment_score_after"] = round(self.alignment_score_after, 2) if self.alignment_score_after is not None else None
            d["angle_score_after"] = round(self.angle_score_after, 2) if self.angle_score_after is not None else None
            d["deformation_after"] = round(self.deformation_after, 2) if self.deformation_after is not None else None
            d["verdict"] = self.verdict
            d["candidates"] = self.candidates
        return d


class PatternRepairEngine:
    """
    Core repair engine executing multi-directional symmetry and topological reconstruction.
    """

    def __init__(self, tolerance: float = 0.20, endpoint_tolerance: float = 0.10):
        self.tolerance = tolerance
        self.endpoint_tolerance = endpoint_tolerance

    def generate_candidates(self, model: CADModel2D) -> List[Any]:
        """Generate multi-hypothesis repair candidates (A, B, C, D)."""
        from src.repair.candidates import CandidateRepairGenerator
        generator = CandidateRepairGenerator()
        return generator.generate_all(model)

    def repair(
        self,
        model: CADModel2D,
        strategy: str = "canonical_intent",
        straighten_boundary: bool = True,
        custom_axis: Optional[SymmetryAxis2D] = None
    ) -> RepairResult:
        """
        Execute repair on CAD model using specified strategy.
        Supported strategies:
          - 'canonical_intent' (Recommended - Multi-hypothesis Regularization & Intent Preservation)
          - '4_quadrant' / '4_quadrant_consensus'
          - 'mirror_left_to_right'
          - 'mirror_right_to_left'
          - 'mirror_bottom_to_top'
          - 'mirror_top_to_bottom'
          - 'canonical_consensus'
        """
        if strategy in ("canonical_intent", "canonical", "auto", "default"):
            from src.repair.candidates import CandidateRepairGenerator
            from src.features.extractor import FeatureExtractor
            from src.intent.detector import DesignIntentDetector

            generator = CandidateRepairGenerator()
            fe = FeatureExtractor()
            features = fe.extract(model)
            intent = DesignIntentDetector().detect_intent(features["lines"], features["loops"], model.bbox)
            candidates = generator.generate_all(model, features=features, intent=intent)

            best_cand = candidates[0]  # sorted by objective cost
            pre_vq = generator.quality_scorer.score(model)
            post_vq = best_cand.quality_score

            ops = [
                f"Design Intent Engine: Identified {len(intent.dominant_angles)} dominant angles, {len(intent.nominal_spacings)} kerf clusters.",
                f"Generated {len(candidates)} competing repair candidates.",
                f"Selected optimal candidate: {best_cand.strategy_name} ({best_cand.description}).",
                f"Objective cost: {best_cand.objective_cost:.2f}, change ratio: {best_cand.change_ratio_percent:.2f}%.",
                f"Visual quality improved from {pre_vq.composite_quality:.2f} to {post_vq.composite_quality:.2f} / 100.",
                f"Deformation penalty: {post_vq.deformation_penalty:.2f} (Zero kinks!).",
                f"Model validation: {'PASSED' if best_cand.validation.is_valid else 'FAILED'} (Watertight: {best_cand.validation.is_watertight})."
            ]

            cand_dicts = [c.to_dict() for c in candidates]

            analyzer = SymmetryAnalyzer(tolerance=self.tolerance, endpoint_tolerance=self.endpoint_tolerance)
            pre_symm = analyzer.analyze(model)
            post_symm = analyzer.analyze(best_cand.repaired_model)

            return RepairResult(
                repaired_model=best_cand.repaired_model,
                strategy_used=best_cand.strategy_name.lower(),
                symmetry_score_before=pre_symm.primary_profile.symmetry_score,
                symmetry_score_after=post_symm.primary_profile.symmetry_score,
                max_deviation_before=pre_symm.primary_profile.max_deviation,
                max_deviation_after=post_symm.primary_profile.max_deviation,
                rms_deviation_before=pre_symm.primary_profile.rms_deviation,
                rms_deviation_after=post_symm.primary_profile.rms_deviation,
                is_watertight=best_cand.validation.is_watertight,
                total_loops_repaired=len(best_cand.repaired_model.lines),
                operations_log=ops,
                visual_quality_before=pre_vq.composite_quality,
                visual_quality_after=post_vq.composite_quality,
                spacing_score_before=pre_vq.spacing_score,
                spacing_score_after=post_vq.spacing_score,
                alignment_score_before=pre_vq.alignment_score,
                alignment_score_after=post_vq.alignment_score,
                angle_score_before=pre_vq.angle_score,
                angle_score_after=post_vq.angle_score,
                deformation_before=pre_vq.deformation_penalty,
                deformation_after=post_vq.deformation_penalty,
                verdict=best_cand.quality_score.verdict,
                candidates=cand_dicts
            )

        ops: List[str] = []

        # 1. Baseline analysis
        analyzer = SymmetryAnalyzer(tolerance=self.tolerance, endpoint_tolerance=self.endpoint_tolerance)
        pre_result = analyzer.analyze(model)

        bbox = model.bbox
        cx = (bbox.min_x + bbox.max_x) * 0.5
        cy = (bbox.min_y + bbox.max_y) * 0.5

        axis = custom_axis or pre_result.primary_axis
        # Snap axis to strict orthogonal lines for CNC panels
        if 45.0 <= axis.angle_degrees <= 135.0:
            axis = SymmetryAxis2D.vertical(cx)
        else:
            axis = SymmetryAxis2D.horizontal(cy)

        ops.append(f"Standardized orthogonal axis: Angle={axis.angle_degrees:.2f}°, Origin=({axis.origin.x:.2f}, {axis.origin.y:.2f})")

        # 2. Extract closed loops
        graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=self.endpoint_tolerance)
        cycle_finder = CycleFinder(graph)
        all_loops = cycle_finder.extract_loops()

        if not all_loops:
            return RepairResult(
                repaired_model=model,
                strategy_used=strategy,
                symmetry_score_before=pre_result.primary_profile.symmetry_score,
                symmetry_score_after=pre_result.primary_profile.symmetry_score,
                max_deviation_before=pre_result.primary_profile.max_deviation,
                max_deviation_after=pre_result.primary_profile.max_deviation,
                rms_deviation_before=pre_result.primary_profile.rms_deviation,
                rms_deviation_after=pre_result.primary_profile.rms_deviation,
                is_watertight=graph.is_watertight,
                total_loops_repaired=0,
                operations_log=["No closed loops found to repair."]
            )

        outer_loop = all_loops[0]
        motif_loops = all_loops[1:] if len(all_loops) > 1 else []
        repaired_loops_points: List[List[Point2D]] = []

        # 3. Outer boundary straightening
        if straighten_boundary and outer_loop:
            straight_outer_pts = self._straighten_outer_boundary(outer_loop, cx, cy, bbox)
            repaired_loops_points.append(straight_outer_pts)
            ops.append(f"Straightened outer frame to orthogonal rectangle {bbox.width:.2f} x {bbox.height:.2f} mm centered at ({cx:.2f}, {cy:.2f}).")
        elif outer_loop:
            repaired_loops_points.append(outer_loop.points)
            ops.append("Preserved original outer boundary.")

        # 4. Dispatch by repair strategy
        if strategy in ("4_quadrant", "4_quadrant_consensus"):
            quad_loops, quad_ops = self._repair_4_quadrant(motif_loops, cx, cy, bbox)
            repaired_loops_points.extend(quad_loops)
            ops.extend(quad_ops)

        elif strategy == "mirror_left_to_right":
            lr_loops, lr_ops = self._repair_bilateral_x(motif_loops, cx, source_side="left")
            repaired_loops_points.extend(lr_loops)
            ops.extend(lr_ops)

        elif strategy == "mirror_right_to_left":
            rl_loops, rl_ops = self._repair_bilateral_x(motif_loops, cx, source_side="right")
            repaired_loops_points.extend(rl_loops)
            ops.extend(rl_ops)

        elif strategy == "mirror_bottom_to_top":
            bt_loops, bt_ops = self._repair_bilateral_y(motif_loops, cy, source_side="bottom")
            repaired_loops_points.extend(bt_loops)
            ops.extend(bt_ops)

        elif strategy == "mirror_top_to_bottom":
            tb_loops, tb_ops = self._repair_bilateral_y(motif_loops, cy, source_side="top")
            repaired_loops_points.extend(tb_loops)
            ops.extend(tb_ops)

        else:  # canonical_consensus fallback
            cons_loops, cons_ops = self._repair_canonical_consensus(motif_loops, axis)
            repaired_loops_points.extend(cons_loops)
            ops.extend(cons_ops)

        # 5. Reconstruct clean CADModel2D
        repaired_lines: List[LineSegment2D] = []
        for loop_pts in repaired_loops_points:
            n = len(loop_pts)
            for i in range(n):
                p1 = loop_pts[i]
                p2 = loop_pts[(i + 1) % n]
                if p1.distance_to(p2) > 1e-4:
                    repaired_lines.append(LineSegment2D(start=p1, end=p2, layer="0"))

        repaired_lines = self._deduplicate_lines(repaired_lines)
        ops.append(f"Topology cleanup: generated {len(repaired_lines)} watertight lines across {len(repaired_loops_points)} closed loops.")

        repaired_model = CADModel2D(
            lines=repaired_lines,
            arcs=[],
            circles=model.circles,
            layers=model.layers,
            source_file=model.source_file,
            units="mm",
            metadata={"repaired": True, "strategy": strategy}
        )

        # 6. Post-repair verification & scoring
        post_result = analyzer.analyze(repaired_model)
        rep_graph = TopologyGraph.from_cad_model(repaired_model, endpoint_tolerance=self.endpoint_tolerance)

        from src.quality.scorer import VisualQualityScorer
        vq_scorer = VisualQualityScorer()
        pre_vq = vq_scorer.score(model, symm_result=pre_result)
        post_vq = vq_scorer.score(repaired_model, symm_result=post_result)

        ops.append(f"Post-repair symmetry score: {post_result.primary_profile.symmetry_score:.2f} / 100")
        ops.append(f"Post-repair max deviation: {post_result.primary_profile.max_deviation:.4f} mm")
        ops.append(f"Post-repair visual quality score: {post_vq.composite_quality:.2f} / 100 (Deformation: {post_vq.deformation_penalty:.2f})")

        return RepairResult(
            repaired_model=repaired_model,
            strategy_used=strategy,
            symmetry_score_before=pre_result.primary_profile.symmetry_score,
            symmetry_score_after=post_result.primary_profile.symmetry_score,
            max_deviation_before=pre_result.primary_profile.max_deviation,
            max_deviation_after=post_result.primary_profile.max_deviation,
            rms_deviation_before=pre_result.primary_profile.rms_deviation,
            rms_deviation_after=post_result.primary_profile.rms_deviation,
            is_watertight=rep_graph.is_watertight,
            total_loops_repaired=len(repaired_loops_points),
            operations_log=ops,
            visual_quality_before=pre_vq.composite_quality,
            visual_quality_after=post_vq.composite_quality,
            spacing_score_before=pre_vq.spacing_score,
            spacing_score_after=post_vq.spacing_score,
            alignment_score_before=pre_vq.alignment_score,
            alignment_score_after=post_vq.alignment_score,
            angle_score_before=pre_vq.angle_score,
            angle_score_after=post_vq.angle_score,
            deformation_before=pre_vq.deformation_penalty,
            deformation_after=post_vq.deformation_penalty,
            verdict=post_vq.verdict
        )

    def _straighten_outer_boundary(self, outer_loop: ClosedLoop, cx: float, cy: float, bbox: BoundingBox2D) -> List[Point2D]:
        """Straighten outer frame to a true orthogonal rectangle centered at (cx, cy)."""
        hw = bbox.width * 0.5
        hh = bbox.height * 0.5
        p1 = Point2D(cx - hw, cy - hh)
        p2 = Point2D(cx + hw, cy - hh)
        p3 = Point2D(cx + hw, cy + hh)
        p4 = Point2D(cx - hw, cy + hh)
        return [p1, p2, p3, p4]
    def _symmetrize_loop_across_axes(
        self,
        pts: List[Point2D],
        cx: float,
        cy: float,
        symm_x: bool = True,
        symm_y: bool = True
    ) -> List[Point2D]:
        """Enforce internal bilateral symmetry across x=cx and/or y=cy without altering orthogonal orientations."""
        pts_out = list(pts)
        if symm_x:
            refl_x = [Point2D(2 * cx - p.x, p.y) for p in pts_out]
            avg_pts = []
            for p in pts_out:
                dists = [p.distance_to(rp) for rp in refl_x]
                idx = int(np.argmin(dists))
                avg_pts.append(Point2D((p.x + refl_x[idx].x) * 0.5, p.y))
            pts_out = avg_pts

        if symm_y:
            refl_y = [Point2D(p.x, 2 * cy - p.y) for p in pts_out]
            avg_pts = []
            for p in pts_out:
                dists = [p.distance_to(rp) for rp in refl_y]
                idx = int(np.argmin(dists))
                avg_pts.append(Point2D(p.x, (p.y + refl_y[idx].y) * 0.5))
            pts_out = avg_pts

        return pts_out

    def _repair_4_quadrant(
        self,
        motifs: List[ClosedLoop],
        cx: float,
        cy: float,
        bbox: BoundingBox2D
    ) -> Tuple[List[List[Point2D]], List[str]]:
        """
        4-fold quadrant symmetry:
        Guarantees all 4 corners (and their respective motifs) are mathematically identical in shape and dimensions.
        """
        ops: List[str] = []
        result_loops: List[List[Point2D]] = []

        # A motif is considered centered or on-axis ONLY if its bounding box physically straddles the axis
        tol = 1.0
        center_motifs: List[ClosedLoop] = []
        v_motifs: List[ClosedLoop] = []
        h_motifs: List[ClosedLoop] = []
        q_motifs: List[ClosedLoop] = []

        for m in motifs:
            b = m.bbox
            straddles_x = (b.min_x < cx - tol) and (b.max_x > cx + tol)
            straddles_y = (b.min_y < cy - tol) and (b.max_y > cy + tol)
            if straddles_x and straddles_y:
                center_motifs.append(m)
            elif straddles_x:
                v_motifs.append(m)
            elif straddles_y:
                h_motifs.append(m)
            else:
                q_motifs.append(m)

        ops.append(f"Categorized motifs: {len(center_motifs)} center, {len(v_motifs)} vertical axis, {len(h_motifs)} horizontal axis, {len(q_motifs)} in 4 quadrants.")

        # 1. Process Center motif(s)
        for cm in center_motifs:
            shift = Vector2D(cx - cm.centroid.x, cy - cm.centroid.y)
            shifted = [p + shift for p in cm.points]
            symm_c = self._symmetrize_loop_across_axes(shifted, cx, cy, symm_x=True, symm_y=True)
            result_loops.append(symm_c)
        if center_motifs:
            ops.append(f"Centered and 4-way symmetrized {len(center_motifs)} central motif(s).")

        # 2. Process V-Axis motifs (bottom half as reference, mirrored to top)
        v_bottom = [m for m in v_motifs if m.centroid.y < cy]
        if not v_bottom:
            v_bottom = v_motifs
        for vm in v_bottom:
            shift = Vector2D(cx - vm.centroid.x, 0.0)
            shifted = [p + shift for p in vm.points]
            symm_v = self._symmetrize_loop_across_axes(shifted, cx, cy, symm_x=True, symm_y=False)
            result_loops.append(symm_v)
            # Mirror to top
            result_loops.append([Point2D(p.x, 2 * cy - p.y) for p in symm_v])
        if v_bottom:
            ops.append(f"Reconstructed {len(v_bottom) * 2} motifs along vertical centerline.")

        # 3. Process H-Axis motifs (left half as reference, mirrored to right)
        h_left = [m for m in h_motifs if m.centroid.x < cx]
        if not h_left:
            h_left = h_motifs
        for hm in h_left:
            shift = Vector2D(0.0, cy - hm.centroid.y)
            shifted = [p + shift for p in hm.points]
            symm_h = self._symmetrize_loop_across_axes(shifted, cx, cy, symm_x=False, symm_y=True)
            result_loops.append(symm_h)
            # Mirror to right
            result_loops.append([Point2D(2 * cx - p.x, p.y) for p in symm_h])
        if h_left:
            ops.append(f"Reconstructed {len(h_left) * 2} motifs along horizontal centerline.")

        # 4. Process Quadrant motifs
        # Motifs in Bottom-Left (Q3: x < cx, y < cy)
        bl_motifs = [m for m in q_motifs if m.centroid.x < cx and m.centroid.y < cy]
        if not bl_motifs:
            # Fallback to any quadrant with motifs
            bl_motifs = [m for m in q_motifs if m.centroid.x < cx] or q_motifs

        # For each quadrant motif in reference quadrant, mirror to all 4 corners
        for qm in bl_motifs:
            pts = qm.points
            # Bottom-Left
            result_loops.append(pts)
            # Bottom-Right
            result_loops.append([Point2D(2 * cx - p.x, p.y) for p in pts])
            # Top-Left
            result_loops.append([Point2D(p.x, 2 * cy - p.y) for p in pts])
            # Top-Right
            result_loops.append([Point2D(2 * cx - p.x, 2 * cy - p.y) for p in pts])

        ops.append(f"Replicated {len(bl_motifs)} reference quadrant motifs across all 4 quadrants ({len(bl_motifs) * 4} identical corner motifs).")

        return result_loops, ops

    def _repair_bilateral_x(
        self,
        motifs: List[ClosedLoop],
        cx: float,
        source_side: str = "left"
    ) -> Tuple[List[List[Point2D]], List[str]]:
        """
        Bilateral symmetry across vertical axis x = cx (Left -> Right or Right -> Left).
        """
        ops: List[str] = []
        result_loops: List[List[Point2D]] = []

        central_loops: List[ClosedLoop] = []
        source_loops: List[ClosedLoop] = []

        for m in motifs:
            straddles = (m.bbox.min_x < cx - 1.0) and (m.bbox.max_x > cx + 1.0)
            if straddles:
                central_loops.append(m)
            elif source_side == "left" and m.centroid.x <= cx:
                source_loops.append(m)
            elif source_side == "right" and m.centroid.x >= cx:
                source_loops.append(m)

        # Central loops symmetrized across x=cx
        for cm in central_loops:
            shift = Vector2D(cx - cm.centroid.x, 0.0)
            shifted = [p + shift for p in cm.points]
            symm_c = self._symmetrize_loop_across_axes(shifted, cx, 0.0, symm_x=True, symm_y=False)
            result_loops.append(symm_c)

        # Source loops preserved and reflected
        for sm in source_loops:
            result_loops.append(sm.points)
            result_loops.append([Point2D(2 * cx - p.x, p.y) for p in sm.points])

        ops.append(f"Mirrored {len(source_loops)} motifs from {source_side.upper()} across vertical axis x={cx:.2f}.")
        if central_loops:
            ops.append(f"Symmetrized {len(central_loops)} central axis motifs across vertical centerline.")

        return result_loops, ops

    def _repair_bilateral_y(
        self,
        motifs: List[ClosedLoop],
        cy: float,
        source_side: str = "bottom"
    ) -> Tuple[List[List[Point2D]], List[str]]:
        """
        Bilateral symmetry across horizontal axis y = cy (Bottom -> Top or Top -> Bottom).
        """
        ops: List[str] = []
        result_loops: List[List[Point2D]] = []

        central_loops: List[ClosedLoop] = []
        source_loops: List[ClosedLoop] = []

        for m in motifs:
            straddles = (m.bbox.min_y < cy - 1.0) and (m.bbox.max_y > cy + 1.0)
            if straddles:
                central_loops.append(m)
            elif source_side == "bottom" and m.centroid.y <= cy:
                source_loops.append(m)
            elif source_side == "top" and m.centroid.y >= cy:
                source_loops.append(m)

        # Central loops symmetrized across y=cy
        for cm in central_loops:
            shift = Vector2D(0.0, cy - cm.centroid.y)
            shifted = [p + shift for p in cm.points]
            symm_c = self._symmetrize_loop_across_axes(shifted, 0.0, cy, symm_x=False, symm_y=True)
            result_loops.append(symm_c)

        # Source loops preserved and reflected
        for sm in source_loops:
            result_loops.append(sm.points)
            result_loops.append([Point2D(p.x, 2 * cy - p.y) for p in sm.points])

        ops.append(f"Mirrored {len(source_loops)} motifs from {source_side.upper()} across horizontal axis y={cy:.2f}.")
        if central_loops:
            ops.append(f"Symmetrized {len(central_loops)} central axis motifs across horizontal centerline.")

        return result_loops, ops

    def _repair_canonical_consensus(
        self,
        motifs: List[ClosedLoop],
        axis: SymmetryAxis2D
    ) -> Tuple[List[List[Point2D]], List[str]]:
        """Averages paired loops across primary symmetry axis."""
        ops: List[str] = []
        result_loops: List[List[Point2D]] = []

        left_loops = [m for m in motifs if axis.reflect_point(m.centroid).x > m.centroid.x]
        right_loops = [m for m in motifs if axis.reflect_point(m.centroid).x < m.centroid.x]
        central_loops = [m for m in motifs if abs(axis.distance_to_point(m.centroid)) <= 10.0]

        paired, unpaired = self._pair_loops(left_loops, right_loops, axis)
        for l_loop, r_loop in paired:
            canon_l, canon_r = self._create_canonical_pair(l_loop, r_loop, axis)
            result_loops.append(canon_l)
            result_loops.append(canon_r)

        for unp in unpaired:
            result_loops.append(unp.points)
            result_loops.append([axis.reflect_point(p) for p in unp.points])

        for c_loop in central_loops:
            result_loops.append(self._symmetrize_central_loop(c_loop, axis))

        ops.append(f"Averaged {len(paired)} motif pairs via canonical consensus.")
        return result_loops, ops

    def _symmetrize_central_loop(self, loop: ClosedLoop, axis: SymmetryAxis2D) -> List[Point2D]:
        pts = loop.points
        c = loop.centroid
        proj_c = axis.project_point(c)
        shift = proj_c - c
        shift_v = Vector2D(shift.x, shift.y)
        centered_pts = [p + shift_v for p in pts]
        refl_pts = [axis.reflect_point(p) for p in centered_pts]

        symm_pts = []
        for pt in centered_pts:
            dists = [pt.distance_to(rp) for rp in refl_pts]
            min_idx = int(np.argmin(dists))
            match_refl = refl_pts[min_idx]
            avg_pt = Point2D((pt.x + match_refl.x) * 0.5, (pt.y + match_refl.y) * 0.5)
            symm_pts.append(avg_pt)
        return symm_pts

    def _pair_loops(self, left_loops: List[ClosedLoop], right_loops: List[ClosedLoop], axis: SymmetryAxis2D):
        paired = []
        unpaired = []
        used_right = set()

        for l in left_loops:
            refl_c = axis.reflect_point(l.centroid)
            best_idx = -1
            min_dist = float("inf")
            for j, r in enumerate(right_loops):
                if j in used_right:
                    continue
                d = refl_c.distance_to(r.centroid)
                if d < min_dist:
                    min_dist = d
                    best_idx = j

            if best_idx != -1 and min_dist < 40.0:
                used_right.add(best_idx)
                paired.append((l, right_loops[best_idx]))
            else:
                unpaired.append(l)

        for j, r in enumerate(right_loops):
            if j not in used_right:
                unpaired.append(r)

        return paired, unpaired

    def _create_canonical_pair(self, l_loop: ClosedLoop, r_loop: ClosedLoop, axis: SymmetryAxis2D) -> Tuple[List[Point2D], List[Point2D]]:
        l_pts = l_loop.points
        refl_r_pts = [axis.reflect_point(p) for p in r_loop.points]

        if len(l_pts) != len(refl_r_pts):
            canon_l = l_pts
        else:
            canon_l = []
            for p1, p2 in zip(l_pts, refl_r_pts):
                canon_l.append(Point2D((p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5))

        canon_r = [axis.reflect_point(p) for p in canon_l]
        return canon_l, canon_r

    def _deduplicate_lines(self, lines: List[LineSegment2D], tol: float = 0.05) -> List[LineSegment2D]:
        """Remove duplicate and reversed coincident line segments."""
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
