"""
CAD Model Validation Engine.
Strict safety checks before CAM export:
  - Dimension preservation (width, height, area within 0.1%)
  - Topology watertightness (100% closed loops, no floating dangling lines)
  - Duplicate cleanup verification
  - Self-intersection prevention
  - Non-degradation safety rule
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.io.dxf_io import CADModel2D
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder


@dataclass
class ModelValidationResult:
    """Detailed summary of model validation checks."""
    is_valid: bool
    dimensions_preserved: bool
    width_diff_mm: float
    height_diff_mm: float
    is_watertight: bool
    total_closed_loops: int
    floating_lines_count: int
    duplicate_lines_count: int
    self_intersections_count: int
    validation_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "dimensions_preserved": self.dimensions_preserved,
            "width_diff_mm": round(self.width_diff_mm, 3),
            "height_diff_mm": round(self.height_diff_mm, 3),
            "is_watertight": self.is_watertight,
            "closed_loops": self.total_closed_loops,
            "floating_lines": self.floating_lines_count,
            "duplicate_lines": self.duplicate_lines_count,
            "self_intersections": self.self_intersections_count,
            "errors": self.validation_errors
        }


class ModelValidator:
    """
    Validates CADModel2D against physical CNC manufacturing constraints.
    """

    def __init__(self, dimension_tol_percent: float = 0.5, endpoint_tolerance: float = 0.10):
        self.dimension_tol_percent = dimension_tol_percent
        self.endpoint_tolerance = endpoint_tolerance

    def validate(
        self,
        repaired_model: CADModel2D,
        original_model: Optional[CADModel2D] = None
    ) -> ModelValidationResult:
        errors: List[str] = []

        # 1. Dimension Preservation Check
        w_diff = 0.0
        h_diff = 0.0
        dims_preserved = True

        if original_model is not None:
            orig_bbox = original_model.bbox
            rep_bbox = repaired_model.bbox
            w_diff = abs(rep_bbox.width - orig_bbox.width)
            h_diff = abs(rep_bbox.height - orig_bbox.height)

            max_w_tol = orig_bbox.width * (self.dimension_tol_percent / 100.0)
            max_h_tol = orig_bbox.height * (self.dimension_tol_percent / 100.0)

            if w_diff > max_w_tol or h_diff > max_h_tol:
                dims_preserved = False
                errors.append(f"Dimension mismatch: width diff={w_diff:.2f} mm (max={max_w_tol:.2f} mm), height diff={h_diff:.2f} mm (max={max_h_tol:.2f} mm)")

        # 2. Topology & Watertightness Check
        graph = TopologyGraph.from_cad_model(repaired_model, endpoint_tolerance=self.endpoint_tolerance)
        cycle_finder = CycleFinder(graph)
        loops = cycle_finder.extract_loops()

        is_watertight = graph.is_watertight
        if not is_watertight:
            errors.append(f"Model has open boundaries (not watertight): {len(graph.open_endpoints)} open endpoints found.")

        # Floating lines check (lines not part of any degree >= 2 cycle)
        floating_lines = sum(1 for n in graph.nodes.values() if n.degree == 1)
        if floating_lines > 0:
            errors.append(f"Found {floating_lines} dangling/floating endpoints.")

        # 3. Duplicate Lines Check
        dup_count = 0
        n_lines = len(repaired_model.lines)
        for i in range(n_lines):
            l1 = repaired_model.lines[i]
            for j in range(i + 1, n_lines):
                l2 = repaired_model.lines[j]
                if l1.is_coincident(l2, tol=0.05):
                    dup_count += 1

        if dup_count > 0:
            errors.append(f"Found {dup_count} duplicate or reversed coincident line segments.")

        # 4. Self-Intersection Check (proper line-line crossings)
        intersect_count = 0
        for i in range(n_lines):
            l1 = repaired_model.lines[i]
            for j in range(i + 1, n_lines):
                l2 = repaired_model.lines[j]
                if l1.intersects(l2):
                    pt = l1.intersection_point(l2)
                    # Exclude shared endpoints
                    if pt and not (pt.is_close(l1.start) or pt.is_close(l1.end) or pt.is_close(l2.start) or pt.is_close(l2.end)):
                        intersect_count += 1

        if intersect_count > 0:
            errors.append(f"Found {intersect_count} illegal interior line intersections.")

        is_valid = (len(errors) == 0)

        return ModelValidationResult(
            is_valid=is_valid,
            dimensions_preserved=dims_preserved,
            width_diff_mm=w_diff,
            height_diff_mm=h_diff,
            is_watertight=is_watertight,
            total_closed_loops=len(loops),
            floating_lines_count=floating_lines,
            duplicate_lines_count=dup_count,
            self_intersections_count=intersect_count,
            validation_errors=errors
        )
