"""
Automated Symmetry Axis Discovery Engine.
Generates multi-source hypotheses (PCA, Centroid, BBox, RANSAC Motif Bisectors)
and refines candidate axes via robust reflection error minimization.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Optional, Dict
import numpy as np
from scipy.optimize import minimize

from src.core.primitives import Point2D, Vector2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.spatial.index import PointSpatialIndex
from src.topology.cycle_finder import ClosedLoop
from src.symmetry.error_metrics import SymmetryEvaluator, SymmetryErrorProfile


class SymmetryAxisFinder:
    """
    Finds dominant symmetry axis/axes in 2D geometry without prior user hints.
    """

    def __init__(self, tolerance: float = 0.20):
        self.tolerance = tolerance

    def find_best_axis(
        self,
        points: List[Point2D],
        loops: Optional[List[ClosedLoop]] = None,
        search_diagonal: bool = True
    ) -> Tuple[SymmetryAxis2D, SymmetryErrorProfile]:
        """
        Find optimal primary symmetry axis for the given point set.
        Returns the best SymmetryAxis2D and its error profile.
        """
        if len(points) < 4:
            # Degenerate case: default to vertical x=0
            ax = SymmetryAxis2D.vertical(0.0)
            evaluator = SymmetryEvaluator(points, loops, self.tolerance)
            return (ax, evaluator.evaluate(ax))

        evaluator = SymmetryEvaluator(points, loops, self.tolerance)
        hypotheses = self._generate_hypotheses(points, loops, search_diagonal)

        # Evaluate all seed hypotheses
        scored_candidates: List[Tuple[SymmetryAxis2D, float, SymmetryErrorProfile]] = []
        for axis in hypotheses:
            profile = evaluator.evaluate(axis)
            # Use RMS deviation as the primary minimization metric
            scored_candidates.append((axis, profile.rms_deviation, profile))

        scored_candidates.sort(key=lambda x: x[1])

        # Refine top 3 best candidates with continuous optimization
        best_axis = scored_candidates[0][0]
        best_profile = scored_candidates[0][2]
        min_error = scored_candidates[0][1]

        top_candidates = scored_candidates[:min(4, len(scored_candidates))]
        for cand_axis, _, _ in top_candidates:
            refined_axis = self._refine_axis(cand_axis, points, evaluator)
            refined_profile = evaluator.evaluate(refined_axis)
            if refined_profile.rms_deviation < min_error:
                min_error = refined_profile.rms_deviation
                best_axis = refined_axis
                best_profile = refined_profile

        return (best_axis, best_profile)

    def find_orthogonal_secondary_axis(
        self,
        primary_axis: SymmetryAxis2D,
        points: List[Point2D],
        loops: Optional[List[ClosedLoop]] = None
    ) -> Optional[Tuple[SymmetryAxis2D, SymmetryErrorProfile]]:
        """
        Check if an orthogonal secondary symmetry axis exists (e.g. horizontal axis for a vertical primary).
        """
        evaluator = SymmetryEvaluator(points, loops, self.tolerance)
        # Orthogonal direction
        ortho_angle = (primary_axis.angle + math.pi * 0.5) % math.pi

        # Seeds along orthogonal direction
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        bbox_center = Point2D((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5)

        seeds = [
            SymmetryAxis2D.from_angle_and_point(Point2D(cx, cy), ortho_angle),
            SymmetryAxis2D.from_angle_and_point(bbox_center, ortho_angle),
        ]

        best_ortho = None
        best_profile = None
        min_err = float("inf")

        for seed in seeds:
            refined = self._refine_axis(seed, points, evaluator)
            prof = evaluator.evaluate(refined)
            if prof.rms_deviation < min_err:
                min_err = prof.rms_deviation
                best_ortho = refined
                best_profile = prof

        # Return secondary axis only if confidence is substantial (> 40%)
        if best_profile and best_profile.confidence > 0.40:
            return (best_ortho, best_profile)
        return None

    def _generate_hypotheses(
        self,
        points: List[Point2D],
        loops: Optional[List[ClosedLoop]],
        search_diagonal: bool
    ) -> List[SymmetryAxis2D]:
        """Generate diverse seed hypotheses from geometric cues."""
        hypotheses: List[SymmetryAxis2D] = []
        xs = np.array([p.x for p in points], dtype=np.float64)
        ys = np.array([p.y for p in points], dtype=np.float64)

        cx = float(np.mean(xs))
        cy = float(np.mean(ys))
        center_pt = Point2D(cx, cy)

        min_x, max_x = float(np.min(xs)), float(np.max(xs))
        min_y, max_y = float(np.min(ys)), float(np.max(ys))
        bbox_center = Point2D((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)

        # 1. Standard Vertical Axis hypotheses
        hypotheses.append(SymmetryAxis2D.vertical(cx))
        hypotheses.append(SymmetryAxis2D.vertical(bbox_center.x))
        hypotheses.append(SymmetryAxis2D.vertical(0.0))

        # 2. Standard Horizontal Axis hypotheses
        hypotheses.append(SymmetryAxis2D.horizontal(cy))
        hypotheses.append(SymmetryAxis2D.horizontal(bbox_center.y))
        hypotheses.append(SymmetryAxis2D.horizontal(0.0))

        # 3. PCA Principal Axes
        coords = np.column_stack([xs - cx, ys - cy])
        cov = np.cov(coords, rowvar=False)
        try:
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
            # Eigenvectors give major and minor principal directions
            v1 = eigenvectors[:, 1]  # Major axis
            v2 = eigenvectors[:, 0]  # Minor axis

            ang1 = math.atan2(v1[1], v1[0]) % math.pi
            ang2 = math.atan2(v2[1], v2[0]) % math.pi

            hypotheses.append(SymmetryAxis2D.from_angle_and_point(center_pt, ang1))
            hypotheses.append(SymmetryAxis2D.from_angle_and_point(center_pt, ang2))
            hypotheses.append(SymmetryAxis2D.from_angle_and_point(bbox_center, ang1))
            hypotheses.append(SymmetryAxis2D.from_angle_and_point(bbox_center, ang2))
        except Exception:
            pass

        # 4. Pairwise Motif Bisectors
        if loops and len(loops) > 2:
            # Sort motif loops by area
            motif_loops = [l for l in loops if l.area < (max_x - min_x) * (max_y - min_y) * 0.8]
            n_motifs = len(motif_loops)
            for i in range(min(n_motifs, 10)):
                for j in range(i + 1, min(n_motifs, 10)):
                    l1 = motif_loops[i]
                    l2 = motif_loops[j]
                    max_a = max(l1.area, l2.area)
                    if max_a > 1e-3 and abs(l1.area - l2.area) / max_a < 0.25:
                        # Similar area motif pair -> compute perpendicular bisector of their centroids
                        c1 = l1.centroid
                        c2 = l2.centroid
                        if c1.distance_to(c2) > 10.0:  # distinct motifs
                            mid = Point2D((c1.x + c2.x) * 0.5, (c1.y + c2.y) * 0.5)
                            # Vector between centroids
                            sep = c2 - c1
                            # Perpendicular bisector direction
                            bisector_dir = sep.perpendicular().normalized()
                            hypotheses.append(SymmetryAxis2D(origin=mid, direction=bisector_dir))

        # 5. Diagonals if requested
        if search_diagonal:
            hypotheses.append(SymmetryAxis2D.from_angle_and_point(center_pt, math.pi * 0.25))
            hypotheses.append(SymmetryAxis2D.from_angle_and_point(center_pt, math.pi * 0.75))

        return hypotheses

    def _refine_axis(
        self,
        seed_axis: SymmetryAxis2D,
        points: List[Point2D],
        evaluator: SymmetryEvaluator
    ) -> SymmetryAxis2D:
        """
        Fine-tune axis origin and angle using Nelder-Mead optimization.
        """
        # Parameterization: [offset along normal, angle_delta]
        init_angle = seed_axis.angle
        init_origin = seed_axis.origin
        normal = seed_axis.normal

        # Subsample points if point count is very large for optimization speed
        subsample = points
        if len(points) > 400:
            step = len(points) // 200
            subsample = points[::step]
        sub_evaluator = SymmetryEvaluator(subsample, tolerance=self.tolerance)

        def loss_fn(params):
            d_norm, d_angle = params
            ang = (init_angle + d_angle) % math.pi
            orig = init_origin + (normal * d_norm)
            ax = SymmetryAxis2D.from_angle_and_point(orig, ang)
            # Compute trimmed mean deviation
            devs = []
            for p in sub_evaluator.sample_points:
                rp = ax.reflect_point(p)
                _, dist, _ = sub_evaluator.spatial_index.nearest(rp)
                devs.append(dist)
            # Use Huber or truncated RMS to be robust against asymmetric outliers
            arr = np.array(devs, dtype=np.float64)
            # Truncate at 90th percentile to ignore extreme outliers
            threshold = np.percentile(arr, 90)
            inliers = arr[arr <= max(2.0, threshold)]
            if len(inliers) == 0:
                return float(np.mean(arr))
            return float(np.mean(inliers ** 2))

        res = minimize(
            loss_fn,
            x0=[0.0, 0.0],
            method="Nelder-Mead",
            options={"maxiter": 60, "xatol": 1e-3, "fatol": 1e-3}
        )

        opt_d_norm, opt_d_angle = res.x
        opt_ang = (init_angle + opt_d_angle) % math.pi
        opt_orig = init_origin + (normal * opt_d_norm)

        # Snap to exact vertical or horizontal if within 2.5 degrees (CNC orthogonal alignment)
        if abs(opt_ang - math.pi * 0.5) < math.radians(2.5):
            return SymmetryAxis2D.vertical(opt_orig.x)
        if opt_ang < math.radians(2.5) or abs(opt_ang - math.pi) < math.radians(2.5):
            return SymmetryAxis2D.horizontal(opt_orig.y)

        return SymmetryAxis2D.from_angle_and_point(opt_orig, opt_ang)
