"""
Rotational and Cyclic Symmetry Detection Engine (C_n and D_n groups).
Analyzes radial patterns (rosettes, medallions, circular panels, round windows)
using Polar Autocorrelation and Angular Fourier Spectrum from the geometric center.
Detects rotational orders n in {2, 3, 4, 5, 6, 8, 10, 12, 16} and distinguishes
pure cyclic rotation (C_n) from dihedral reflectional-rotational symmetry (D_n).
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
import numpy as np
from scipy.spatial import cKDTree

from src.core.primitives import Point2D, Vector2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D


@dataclass
class RotationalSymmetryProfile:
    """Quantitative results of rotational/cyclic symmetry analysis."""
    center: Point2D
    symmetry_group: str          # e.g. "C4", "C8", "D4", "D8", "None"
    order: int                   # Rotational fold order n (1 = no rotational symmetry)
    is_dihedral: bool            # True if also possesses reflectional symmetry across radial axes
    step_angle_deg: float        # Fundamental angle of rotation = 360 / order
    confidence: float            # 0.0 to 1.0
    rms_deviation: float         # Mean squared distance error in mm
    max_deviation: float         # Maximum error in mm
    matched_ratio: float         # Proportion of points matched under rotation
    reflection_axes: List[SymmetryAxis2D] = field(default_factory=list)
    fourier_peaks: Dict[int, float] = field(default_factory=dict)

    @property
    def group(self) -> str:
        return self.symmetry_group

    @property
    def has_reflection(self) -> bool:
        return self.is_dihedral

    def __len__(self) -> int:
        return 1 if self.order > 1 else 0

    def __getitem__(self, index: int) -> RotationalSymmetryProfile:
        if index == 0:
            return self
        raise IndexError("RotationalSymmetryProfile index out of range")

    def __iter__(self):
        if self.order > 1:
            yield self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "center": self.center.to_dict(),
            "symmetry_group": self.symmetry_group,
            "order": self.order,
            "is_dihedral": self.is_dihedral,
            "step_angle_deg": round(self.step_angle_deg, 2),
            "confidence": round(self.confidence, 4),
            "rms_deviation_mm": round(self.rms_deviation, 4),
            "max_deviation_mm": round(self.max_deviation, 4),
            "matched_ratio": round(self.matched_ratio, 4),
            "reflection_axes_count": len(self.reflection_axes),
            "fourier_peaks": {str(k): round(v, 2) for k, v in self.fourier_peaks.items()}
        }


class RotationalSymmetryDetector:
    """
    Detects cyclic (C_n) and dihedral (D_n) symmetries in 2D point sets and CAD models.
    """

    SUPPORTED_ORDERS = [2, 3, 4, 5, 6, 8, 10, 12, 16]

    def __init__(self, tolerance: float = 0.20, num_angular_bins: int = 180):
        self.tolerance = tolerance
        self.num_bins = num_angular_bins

    def detect(
        self,
        points: Union[List[Point2D], Any],
        center: Optional[Point2D] = None
    ) -> RotationalSymmetryProfile:
        """
        Detects dominant rotational symmetry group and order for the given point set or CADModel2D.
        """
        if hasattr(points, "get_all_sampled_points"):
            pts = points.get_all_sampled_points(num_samples_per_entity=12)
        elif hasattr(points, "lines"):
            pts = []
            for l in points.lines:
                pts.extend(l.sample_points(8))
        else:
            pts = list(points)

        if len(pts) < 8:
            origin = center or (pts[0] if pts else Point2D(0.0, 0.0))
            return RotationalSymmetryProfile(
                center=origin, symmetry_group="None", order=1, is_dihedral=False,
                step_angle_deg=360.0, confidence=0.0, rms_deviation=0.0,
                max_deviation=0.0, matched_ratio=0.0
            )

        xs = np.array([p.x for p in pts], dtype=np.float64)
        ys = np.array([p.y for p in pts], dtype=np.float64)

        if center is None:
            cx = float(np.mean(xs))
            cy = float(np.mean(ys))
            center = Point2D(cx, cy)
        else:
            cx, cy = center.x, center.y

        coords = np.column_stack((xs - cx, ys - cy))
        radii = np.hypot(coords[:, 0], coords[:, 1])
        angles = (np.arctan2(coords[:, 1], coords[:, 0]) % (2.0 * math.pi))

        # Filter points extremely close to center (which are invariant to rotation)
        mask = radii > max(0.5, self.tolerance * 2.0)
        if np.count_nonzero(mask) < 6:
            return RotationalSymmetryProfile(
                center=center, symmetry_group="None", order=1, is_dihedral=False,
                step_angle_deg=360.0, confidence=0.0, rms_deviation=0.0,
                max_deviation=0.0, matched_ratio=0.0
            )

        active_angles = angles[mask]
        active_radii = radii[mask]
        active_coords = coords[mask]

        # 1. Angular Fourier Spectrum analysis
        bin_indices = np.floor((active_angles / (2.0 * math.pi)) * self.num_bins).astype(int)
        bin_indices = np.clip(bin_indices, 0, self.num_bins - 1)

        hist = np.zeros(self.num_bins, dtype=np.float64)
        np.add.at(hist, bin_indices, 1.0)

        # Smooth histogram slightly to handle noise
        kernel = np.array([0.25, 0.5, 0.25])
        hist_smooth = np.convolve(np.tile(hist, 3), kernel, mode='same')[self.num_bins:2*self.num_bins]

        fft_vals = np.abs(np.fft.rfft(hist_smooth))
        fourier_peaks: Dict[int, float] = {}
        for n in self.SUPPORTED_ORDERS:
            if n < len(fft_vals):
                fourier_peaks[n] = float(fft_vals[n])

        # 2. KD-Tree Verification of candidate orders
        tree = cKDTree(active_coords)
        best_order = 1
        best_rms = float("inf")
        best_max = 0.0
        best_matched = 0.0
        best_conf = 0.0

        # Sort candidate orders by Fourier power
        sorted_orders = sorted(self.SUPPORTED_ORDERS, key=lambda o: fourier_peaks.get(o, 0.0), reverse=True)

        for n in sorted_orders:
            step_rad = 2.0 * math.pi / n
            cos_a = math.cos(step_rad)
            sin_a = math.sin(step_rad)
            rot_matrix = np.array([[cos_a, -sin_a], [sin_a, cos_a]])

            # Rotate coordinates by fundamental step
            rotated_coords = active_coords @ rot_matrix.T
            distances, _ = tree.query(rotated_coords, k=1)

            matched_count = int(np.count_nonzero(distances <= self.tolerance))
            matched_ratio = matched_count / len(active_coords)
            rms = float(np.sqrt(np.mean(distances ** 2)))
            max_dev = float(np.max(distances))

            # Confidence based on matched ratio and RMS relative to tolerance
            conf = matched_ratio * math.exp(-rms / max(0.5, self.tolerance * 3.0))

            if matched_ratio >= 0.65:
                is_higher_multiple = (best_order > 1 and n > best_order and n % best_order == 0 and conf >= best_conf - 0.03)
                is_subgroup = (best_order > 1 and n < best_order and best_order % n == 0)

                if is_subgroup:
                    continue

                if is_higher_multiple or conf > best_conf + 0.03 or (best_conf == 0.0 and conf > 0.5):
                    best_order = n
                    best_rms = rms
                    best_max = max_dev
                    best_matched = matched_ratio
                    best_conf = conf

        # 3. Check for Dihedral reflection axes (D_n vs C_n)
        reflection_axes: List[SymmetryAxis2D] = []
        is_dihedral = False

        if best_order > 1:
            step_rad = 2.0 * math.pi / best_order
            # Check candidate reflection axis angles
            for k in range(best_order):
                axis_ang = (k * step_rad * 0.5) % math.pi
                ax = SymmetryAxis2D.from_angle_and_point(center, axis_ang)
                # Test reflection
                dx = coords[:, 0]
                dy = coords[:, 1]
                proj = dx * ax.direction.dx + dy * ax.direction.dy
                refl_coords = np.column_stack((
                    2 * proj * ax.direction.dx - dx,
                    2 * proj * ax.direction.dy - dy
                ))
                refl_dists, _ = tree.query(refl_coords, k=1)
                refl_match = np.count_nonzero(refl_dists <= self.tolerance) / len(active_coords)
                if refl_match >= 0.60:
                    reflection_axes.append(ax)

            if len(reflection_axes) >= max(1, best_order // 2):
                is_dihedral = True

        group_name = f"D{best_order}" if is_dihedral else (f"C{best_order}" if best_order > 1 else "None")

        return RotationalSymmetryProfile(
            center=center,
            symmetry_group=group_name,
            order=best_order,
            is_dihedral=is_dihedral,
            step_angle_deg=360.0 / best_order,
            confidence=best_conf,
            rms_deviation=best_rms if best_order > 1 else 0.0,
            max_deviation=best_max if best_order > 1 else 0.0,
            matched_ratio=best_matched if best_order > 1 else 0.0,
            reflection_axes=reflection_axes,
            fourier_peaks=fourier_peaks
        )
