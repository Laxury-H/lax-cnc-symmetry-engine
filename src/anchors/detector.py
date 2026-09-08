"""
Design Anchor Detector.
Identifies invariant reference landmarks (corners, center, axis intersections, boundary midpoints)
that anchor the physical stock and design intent during geometric regularization.
"""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from src.core.primitives import Point2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.io.dxf_io import CADModel2D
from src.features.extractor import LoopFeature


class AnchorType(Enum):
    OUTER_CORNER = "OUTER_CORNER"
    PANEL_CENTER = "PANEL_CENTER"
    BOUNDARY_MIDPOINT = "BOUNDARY_MIDPOINT"
    AXIS_INTERSECTION = "AXIS_INTERSECTION"
    MOTIF_CENTER = "MOTIF_CENTER"


class AnchorImportance(Enum):
    FIXED = "FIXED"       # Must NOT be modified (e.g. physical stock bounds, panel center)
    MAJOR = "MAJOR"       # High structural anchor (e.g. main axes intersections, primary box centers)
    SOFT = "SOFT"         # Adaptable anchor (e.g. secondary motif centroids, movable joints)


@dataclass
class DesignAnchor:
    """Invariant geometric landmark."""
    anchor_id: str
    point: Point2D
    anchor_type: AnchorType
    importance: AnchorImportance
    confidence: float = 1.0
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "x": round(self.point.x, 3),
            "y": round(self.point.y, 3),
            "type": self.anchor_type.value,
            "importance": self.importance.value,
            "confidence": round(self.confidence, 3),
            "description": self.description
        }


class AnchorDetector:
    """
    Detects design anchors from CAD model, extracted loops, and symmetry axes.
    """

    def __init__(self, tolerance: float = 0.20):
        self.tolerance = tolerance

    def detect_anchors(
        self,
        model: CADModel2D,
        loops: Optional[List[LoopFeature]] = None,
        primary_axis: Optional[SymmetryAxis2D] = None,
        secondary_axis: Optional[SymmetryAxis2D] = None
    ) -> List[DesignAnchor]:
        anchors: List[DesignAnchor] = []
        bbox = model.bbox
        cx = (bbox.min_x + bbox.max_x) * 0.5
        cy = (bbox.min_y + bbox.max_y) * 0.5

        # 1. Panel Center (FIXED)
        anchors.append(DesignAnchor(
            anchor_id="anchor_panel_center",
            point=Point2D(cx, cy),
            anchor_type=AnchorType.PANEL_CENTER,
            importance=AnchorImportance.FIXED,
            confidence=1.0,
            description="True center of CNC panel bounding stock"
        ))

        # 2. Four Outer Frame Corners (FIXED)
        anchors.append(DesignAnchor(
            anchor_id="anchor_outer_bottom_left",
            point=Point2D(bbox.min_x, bbox.min_y),
            anchor_type=AnchorType.OUTER_CORNER,
            importance=AnchorImportance.FIXED,
            confidence=1.0,
            description="Outer frame bottom-left corner"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_outer_bottom_right",
            point=Point2D(bbox.max_x, bbox.min_y),
            anchor_type=AnchorType.OUTER_CORNER,
            importance=AnchorImportance.FIXED,
            confidence=1.0,
            description="Outer frame bottom-right corner"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_outer_top_right",
            point=Point2D(bbox.max_x, bbox.max_y),
            anchor_type=AnchorType.OUTER_CORNER,
            importance=AnchorImportance.FIXED,
            confidence=1.0,
            description="Outer frame top-right corner"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_outer_top_left",
            point=Point2D(bbox.min_x, bbox.max_y),
            anchor_type=AnchorType.OUTER_CORNER,
            importance=AnchorImportance.FIXED,
            confidence=1.0,
            description="Outer frame top-left corner"
        ))

        # 3. Outer Frame Midpoints (MAJOR)
        anchors.append(DesignAnchor(
            anchor_id="anchor_mid_bottom",
            point=Point2D(cx, bbox.min_y),
            anchor_type=AnchorType.BOUNDARY_MIDPOINT,
            importance=AnchorImportance.MAJOR,
            confidence=0.98,
            description="Outer frame bottom centerline midpoint"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_mid_top",
            point=Point2D(cx, bbox.max_y),
            anchor_type=AnchorType.BOUNDARY_MIDPOINT,
            importance=AnchorImportance.MAJOR,
            confidence=0.98,
            description="Outer frame top centerline midpoint"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_mid_left",
            point=Point2D(bbox.min_x, cy),
            anchor_type=AnchorType.BOUNDARY_MIDPOINT,
            importance=AnchorImportance.MAJOR,
            confidence=0.98,
            description="Outer frame left centerline midpoint"
        ))
        anchors.append(DesignAnchor(
            anchor_id="anchor_mid_right",
            point=Point2D(bbox.max_x, cy),
            anchor_type=AnchorType.BOUNDARY_MIDPOINT,
            importance=AnchorImportance.MAJOR,
            confidence=0.98,
            description="Outer frame right centerline midpoint"
        ))

        # 4. Central Motif Center (if present)
        if loops:
            for loop in loops:
                if loop.loop_category == "CENTER_BOX":
                    anchors.append(DesignAnchor(
                        anchor_id="anchor_motif_center_box",
                        point=loop.centroid,
                        anchor_type=AnchorType.MOTIF_CENTER,
                        importance=AnchorImportance.MAJOR,
                        confidence=0.95,
                        description="Central decorative box centroid"
                    ))
                elif loop.loop_category == "CORNER_BOX":
                    anchors.append(DesignAnchor(
                        anchor_id=f"anchor_{loop.feature_id}",
                        point=loop.centroid,
                        anchor_type=AnchorType.MOTIF_CENTER,
                        importance=AnchorImportance.SOFT,
                        confidence=0.90,
                        description=f"Corner box centroid ({loop.feature_id})"
                    ))

        return anchors
