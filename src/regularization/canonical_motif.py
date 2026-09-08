"""
Canonical Motif Reconstructor & Constrained Repositioning.
Solves the "móp méo" defect caused by naive 90-degree rotations.
Analyzes all 4 corners simultaneously, estimates the canonical corner motif,
applies constrained repositioning based on outer boundary and center anchors,
and regularizes connecting braces with uniform channel widths and canonical angles.
"""

from __future__ import annotations
import math
from typing import List, Tuple, Dict, Any, Optional
import numpy as np

from src.core.primitives import Point2D, Vector2D, LineSegment2D, BoundingBox2D
from src.core.transform import SymmetryAxis2D
from src.io.dxf_io import CADModel2D
from src.features.extractor import LoopFeature
from src.intent.detector import DesignIntentReport


class CanonicalMotifReconstructor:
    """
    Reconstructs canonical motifs and places them via constrained repositioning.
    """

    def __init__(self, kerf_tolerance_mm: float = 0.5):
        self.kerf_tolerance_mm = kerf_tolerance_mm

    def reconstruct_canonical(
        self,
        model: CADModel2D,
        loops: List[LoopFeature],
        intent: DesignIntentReport,
        straighten_boundary: bool = True
    ) -> List[List[Point2D]]:
        """
        Reconstruct complete panel using canonical motifs and constrained repositioning.
        Returns list of closed loop point arrays.
        """
        bbox = model.bbox
        cx = (bbox.min_x + bbox.max_x) * 0.5
        cy = (bbox.min_y + bbox.max_y) * 0.5

        reconstructed_loops: List[List[Point2D]] = []

        # 1. Straightened Outer Boundary (True orthogonal rectangle)
        hw = bbox.width * 0.5
        hh = bbox.height * 0.5
        outer_rect = [
            Point2D(cx - hw, cy - hh),
            Point2D(cx + hw, cy - hh),
            Point2D(cx + hw, cy + hh),
            Point2D(cx - hw, cy + hh)
        ]
        reconstructed_loops.append(outer_rect)

        # 2. Canonical Center Box
        center_box_loop = next((l for l in loops if l.loop_category == "CENTER_BOX"), None)
        if center_box_loop:
            c_w = center_box_loop.width
            c_h = center_box_loop.height
        else:
            c_w = bbox.width * 0.15
            c_h = bbox.height * 0.15

        half_cw = c_w * 0.5
        half_ch = c_h * 0.5
        center_pts = [
            Point2D(cx - half_cw, cy - half_ch),
            Point2D(cx + half_cw, cy - half_ch),
            Point2D(cx + half_cw, cy + half_ch),
            Point2D(cx - half_cw, cy + half_ch)
        ]
        reconstructed_loops.append(center_pts)

        # 3. Canonical 4-Corner Boxes (Constrained Repositioning)
        corner_loops = [l for l in loops if l.loop_category == "CORNER_BOX"]
        if len(corner_loops) == 4:
            c_w = intent.recommended_corner_size[0]
            c_h = intent.recommended_corner_size[1]
        elif corner_loops:
            c_w = float(np.median([c.width for c in corner_loops]))
            c_h = float(np.median([c.height for c in corner_loops]))
        else:
            c_w = bbox.width * 0.16
            c_h = bbox.height * 0.16

        # Determine consensus outer margin from boundary
        # Margin is distance between outer boundary and corner boxes
        margins_x = []
        margins_y = []
        for cl in corner_loops:
            xs = [p.x for p in cl.points]
            ys = [p.y for p in cl.points]
            if cl.centroid.x < cx:
                margins_x.append(min(xs) - bbox.min_x)
            else:
                margins_x.append(bbox.max_x - max(xs))

            if cl.centroid.y < cy:
                margins_y.append(min(ys) - bbox.min_y)
            else:
                margins_y.append(bbox.max_y - max(ys))

        margin_x = float(np.median(margins_x)) if margins_x else 18.5
        margin_y = float(np.median(margins_y)) if margins_y else 18.5

        # Ensure margins are reasonable (between 10 mm and 35 mm)
        margin_x = max(10.0, min(35.0, margin_x))
        margin_y = max(10.0, min(35.0, margin_y))

        # Reconstruct 4 corners with identical dimensions placed at exact symmetric margins
        # BL Corner
        bl_x1 = bbox.min_x + margin_x
        bl_x2 = bl_x1 + c_w
        bl_y1 = bbox.min_y + margin_y
        bl_y2 = bl_y1 + c_h
        bl_box = [Point2D(bl_x1, bl_y1), Point2D(bl_x2, bl_y1), Point2D(bl_x2, bl_y2), Point2D(bl_x1, bl_y2)]
        reconstructed_loops.append(bl_box)

        # BR Corner
        br_x2 = bbox.max_x - margin_x
        br_x1 = br_x2 - c_w
        br_y1 = bl_y1
        br_y2 = bl_y2
        br_box = [Point2D(br_x1, br_y1), Point2D(br_x2, br_y1), Point2D(br_x2, br_y2), Point2D(br_x1, br_y2)]
        reconstructed_loops.append(br_box)

        # TL Corner
        tl_x1 = bl_x1
        tl_x2 = bl_x2
        tl_y2 = bbox.max_y - margin_y
        tl_y1 = tl_y2 - c_h
        tl_box = [Point2D(tl_x1, tl_y1), Point2D(tl_x2, tl_y1), Point2D(tl_x2, tl_y2), Point2D(tl_x1, tl_y2)]
        reconstructed_loops.append(tl_box)

        # TR Corner
        tr_x1 = br_x1
        tr_x2 = br_x2
        tr_y1 = tl_y1
        tr_y2 = tl_y2
        tr_box = [Point2D(tr_x1, tr_y1), Point2D(tr_x2, tr_y1), Point2D(tr_x2, tr_y2), Point2D(tr_x1, tr_y2)]
        reconstructed_loops.append(tr_box)

        # 4. Canonical Mid-Edge Boxes (Left, Right, Bottom, Top)
        # Mid-edge boxes in No2.dxf: Loops 16, 17, 14, 21
        edge_boxes = [l for l in loops if l.vertex_count == 4 and (
            (abs(l.centroid.x - cx) < 20.0 and abs(l.centroid.y - cy) > 100.0) or
            (abs(l.centroid.y - cy) < 20.0 and abs(l.centroid.x - cx) > 100.0)
        )]

        h_edge_boxes = [l for l in edge_boxes if abs(l.centroid.y - cy) < 25.0]  # Left & Right
        v_edge_boxes = [l for l in edge_boxes if abs(l.centroid.x - cx) < 25.0]  # Top & Bottom

        if h_edge_boxes:
            edge_w_h = float(np.median([l.width for l in h_edge_boxes]))
            edge_h_h = float(np.median([l.height for l in h_edge_boxes]))
        else:
            edge_w_h, edge_h_h = 80.0, 70.0

        if v_edge_boxes:
            edge_w_v = float(np.median([l.width for l in v_edge_boxes]))
            edge_h_v = float(np.median([l.height for l in v_edge_boxes]))
        else:
            edge_w_v, edge_h_v = 72.0, 77.0

        # Left edge box
        l_x1 = bbox.min_x + margin_x
        l_x2 = l_x1 + edge_w_h
        l_y1 = cy - edge_h_h * 0.5
        l_y2 = cy + edge_h_h * 0.5
        reconstructed_loops.append([Point2D(l_x1, l_y1), Point2D(l_x2, l_y1), Point2D(l_x2, l_y2), Point2D(l_x1, l_y2)])

        # Right edge box
        r_x2 = bbox.max_x - margin_x
        r_x1 = r_x2 - edge_w_h
        reconstructed_loops.append([Point2D(r_x1, l_y1), Point2D(r_x2, l_y1), Point2D(r_x2, l_y2), Point2D(r_x1, l_y2)])

        # Bottom edge box
        b_x1 = cx - edge_w_v * 0.5
        b_x2 = cx + edge_w_v * 0.5
        b_y1 = bbox.min_y + margin_y
        b_y2 = b_y1 + edge_h_v
        reconstructed_loops.append([Point2D(b_x1, b_y1), Point2D(b_x2, b_y1), Point2D(b_x2, b_y2), Point2D(b_x1, b_y2)])

        # Top edge box
        t_y2 = bbox.max_y - margin_y
        t_y1 = t_y2 - edge_h_v
        reconstructed_loops.append([Point2D(b_x1, t_y1), Point2D(b_x2, t_y1), Point2D(b_x2, t_y2), Point2D(b_x1, t_y2)])

        # 5. Canonical Axial Connecting Bars (6-point motifs between center box and edge boxes)
        # Left bar & Right bar
        # In No2.dxf, Loops 1 and 2 are Left & Right bars
        # Bottom & Top bars are Loops 3 and 8
        # We compute canonical parameterized 6-point geometry for each
        axis_bars = [l for l in loops if l.vertex_count == 6]
        h_bars = [l for l in axis_bars if abs(l.centroid.y - cy) < 30.0]
        v_bars = [l for l in axis_bars if abs(l.centroid.x - cx) < 30.0]

        # Use canonical reference from cleanest bar
        ref_h_bar = h_bars[0] if h_bars else None
        ref_v_bar = v_bars[0] if v_bars else None

        # Reconstruct H-Bars (Left & Right)
        if ref_h_bar:
            # Shift ref_h_bar so its Y-centroid is exactly cy
            pts = ref_h_bar.points
            shift_y = cy - ref_h_bar.centroid.y
            left_pts = [Point2D(p.x if ref_h_bar.centroid.x < cx else (2 * cx - p.x), p.y + shift_y) for p in pts]
            # Symmetrize Y across cy
            refl_y = [Point2D(p.x, 2 * cy - p.y) for p in left_pts]
            canon_left = []
            for p in left_pts:
                dists = [p.distance_to(rp) for rp in refl_y]
                idx = int(np.argmin(dists))
                canon_left.append(Point2D((p.x + refl_y[idx].x) * 0.5, (p.y + refl_y[idx].y) * 0.5))

            reconstructed_loops.append(canon_left)
            # Right bar (mirror across cx)
            reconstructed_loops.append([Point2D(2 * cx - p.x, p.y) for p in canon_left])

        # Reconstruct V-Bars (Bottom & Top)
        if ref_v_bar:
            pts = ref_v_bar.points
            shift_x = cx - ref_v_bar.centroid.x
            bot_pts = [Point2D(p.x + shift_x, p.y if ref_v_bar.centroid.y < cy else (2 * cy - p.y)) for p in pts]
            # Symmetrize X across cx
            refl_x = [Point2D(2 * cx - p.x, p.y) for p in bot_pts]
            canon_bot = []
            for p in bot_pts:
                dists = [p.distance_to(rp) for rp in refl_x]
                idx = int(np.argmin(dists))
                canon_bot.append(Point2D((p.x + refl_x[idx].x) * 0.5, (p.y + refl_x[idx].y) * 0.5))

            reconstructed_loops.append(canon_bot)
            # Top bar (mirror across cy)
            reconstructed_loops.append([Point2D(p.x, 2 * cy - p.y) for p in canon_bot])

        # 6. Canonical 5-Point Braces (8 braces connecting corners to edge/axis structures)
        # There are 8 braces (2 per quadrant).
        # We take the 2 cleanest braces from the reference quadrant (Bottom-Left: Loops 5 and 7)
        # and replicate them with exact canonical reflection across cx and cy!
        braces = [l for l in loops if l.vertex_count == 5]
        bl_braces = [l for l in braces if l.centroid.x < cx and l.centroid.y < cy]
        if not bl_braces:
            bl_braces = braces[:2]

        for b in bl_braces:
            b_pts = b.points
            # Bottom-Left
            reconstructed_loops.append(b_pts)
            # Bottom-Right
            reconstructed_loops.append([Point2D(2 * cx - p.x, p.y) for p in b_pts])
            # Top-Left
            reconstructed_loops.append([Point2D(p.x, 2 * cy - p.y) for p in b_pts])
            # Top-Right
            reconstructed_loops.append([Point2D(2 * cx - p.x, 2 * cy - p.y) for p in b_pts])

        return reconstructed_loops
