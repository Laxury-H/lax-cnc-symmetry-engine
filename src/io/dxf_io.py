"""
DXF Importer and Exporter for CNC machining workflows.
Guarantees exact millimeter units, layer separation, and primitive entity fidelity.
"""

from __future__ import annotations
import math
import os
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set, Dict, Any
import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic

from src.core.primitives import Point2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D


@dataclass
class CADModel2D:
    """In-memory 2D CAD representation of pattern geometry."""
    lines: List[LineSegment2D] = field(default_factory=list)
    arcs: List[Arc2D] = field(default_factory=list)
    circles: List[Circle2D] = field(default_factory=list)
    layers: Set[str] = field(default_factory=set)
    source_file: str = ""
    units: str = "mm"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_entities(self) -> int:
        return len(self.lines) + len(self.arcs) + len(self.circles)

    @property
    def bbox(self) -> BoundingBox2D:
        all_pts: List[Point2D] = []
        for l in self.lines:
            all_pts.append(l.start)
            all_pts.append(l.end)
        for a in self.arcs:
            all_pts.extend(a.sample_points(8))
        for c in self.circles:
            all_pts.append(Point2D(c.center.x - c.radius, c.center.y - c.radius))
            all_pts.append(Point2D(c.center.x + c.radius, c.center.y + c.radius))
        return BoundingBox2D.from_points(all_pts)

    def get_all_sampled_points(self, num_samples_per_entity: int = 10) -> List[Point2D]:
        """Sample discrete points from all entities for spatial/symmetry calculations."""
        pts: List[Point2D] = []
        for l in self.lines:
            pts.extend(l.sample_points(num_samples_per_entity))
        for a in self.arcs:
            pts.extend(a.sample_points(num_samples_per_entity * 2))
        for c in self.circles:
            pts.extend(c.sample_points(num_samples_per_entity * 3))
        return pts


class DXFImporter:
    """Reads DXF files and extracts CADModel2D with millimeter unit normalization."""

    INSUNITS_MAP = {
        0: ("unitless", 1.0),
        1: ("inches", 25.4),
        2: ("feet", 304.8),
        3: ("miles", 1.60934e6),
        4: ("millimeters", 1.0),
        5: ("centimeters", 10.0),
        6: ("meters", 1000.0),
    }

    def __init__(self, target_unit: str = "mm"):
        self.target_unit = target_unit

    def load(self, filepath: str) -> CADModel2D:
        """Load DXF file and parse entities into CADModel2D."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"DXF file not found: {filepath}")

        doc = ezdxf.readfile(filepath)
        return self.load_document(doc, filepath)

    def load_document(self, doc: Drawing, filepath: str = "") -> CADModel2D:
        """Use the same geometry extraction for native DXF and converted DWG."""
        msp = doc.modelspace()

        # Determine unit scale factor
        scale_factor = 1.0
        header_unit = "millimeters"
        from ezdxf import units
        insunits = doc.header.get("$INSUNITS", 0)
        header_unit = units.unit_name(insunits)
        if insunits:
            scale_factor = units.conversion_factor(insunits, 4)

        model = CADModel2D(
            source_file=filepath,
            units="mm",
            metadata={"header_unit": header_unit, "scale_factor": scale_factor, "dxf_version": doc.dxfversion}
        )

        skipped = {}
        projected_3d = False
        def expand(entities, depth=0, inherited_layer="0"):
            if depth > 32:
                raise ValueError("Bản vẽ có quá nhiều cấp block lồng nhau.")
            for item in entities:
                if item.dxftype() == "INSERT":
                    def on_skip(entity, reason):
                        key = entity.dxftype()
                        skipped[key] = skipped.get(key, 0) + 1
                    inserts = item.multi_insert() if item.mcount > 1 else [item]
                    for insert in inserts:
                        yield from expand(insert.virtual_entities(skipped_entity_callback=on_skip), depth + 1,
                                          insert.dxf.layer if insert.dxf.layer != "0" else inherited_layer)
                else:
                    yield item, item.dxf.layer if item.dxf.layer != "0" else inherited_layer

        for entity, layer in expand(msp):
            dxftype = entity.dxftype()
            model.layers.add(layer)
            if dxftype in {"ARC", "CIRCLE", "LWPOLYLINE", "POLYLINE"}:
                extrusion = entity.dxf.get("extrusion", (0, 0, 1))
                if tuple(extrusion) != (0, 0, 1):
                    key = dxftype + " (mặt phẳng OCS khác XY)"
                    skipped[key] = skipped.get(key, 0) + 1
                    continue
            if dxftype == "POLYLINE" and (entity.is_polygon_mesh or entity.is_poly_face_mesh):
                skipped["MESH"] = skipped.get("MESH", 0) + 1
                continue
            for attribute in ("start", "end", "center", "elevation"):
                value = entity.dxf.get(attribute) if entity.dxf.is_supported(attribute) else None
                if value is not None and (getattr(value, "z", 0) or (attribute == "elevation" and isinstance(value, (float, int)) and value)):
                    projected_3d = True

            if dxftype == "LINE":
                p1 = Point2D(entity.dxf.start.x * scale_factor, entity.dxf.start.y * scale_factor)
                p2 = Point2D(entity.dxf.end.x * scale_factor, entity.dxf.end.y * scale_factor)
                model.lines.append(LineSegment2D(
                    start=p1,
                    end=p2,
                    layer=layer,
                    entity_id=str(entity.dxf.handle)
                ))

            elif dxftype == "ARC":
                center = Point2D(entity.dxf.center.x * scale_factor, entity.dxf.center.y * scale_factor)
                radius = entity.dxf.radius * scale_factor
                start_rad = math.radians(entity.dxf.start_angle)
                end_rad = math.radians(entity.dxf.end_angle)
                model.arcs.append(Arc2D(
                    center=center,
                    radius=radius,
                    start_angle=start_rad,
                    end_angle=end_rad,
                    is_ccw=True,
                    layer=layer,
                    entity_id=str(entity.dxf.handle)
                ))

            elif dxftype == "CIRCLE":
                center = Point2D(entity.dxf.center.x * scale_factor, entity.dxf.center.y * scale_factor)
                radius = entity.dxf.radius * scale_factor
                model.circles.append(Circle2D(
                    center=center,
                    radius=radius,
                    layer=layer,
                    entity_id=str(entity.dxf.handle)
                ))

            elif dxftype == "LWPOLYLINE":
                # Explode polyline into lines and arcs with bulge handling
                poly_lines, poly_arcs = self._explode_lwpolyline(entity, scale_factor, layer)
                model.lines.extend(poly_lines)
                model.arcs.extend(poly_arcs)

            elif dxftype == "POLYLINE":
                poly_lines, poly_arcs = self._explode_polyline2d(entity, scale_factor, layer)
                model.lines.extend(poly_lines)
                model.arcs.extend(poly_arcs)

            elif dxftype == "SPLINE":
                # Discretize spline as connected line segments
                spline_lines = self._approximate_spline(entity, scale_factor, layer)
                model.lines.extend(spline_lines)

            elif dxftype == "ELLIPSE":
                pts = [Point2D(p.x * scale_factor, p.y * scale_factor)
                       for p in entity.flattening(0.02 / scale_factor)]
                model.lines.extend(LineSegment2D(a, b, layer=layer) for a, b in zip(pts, pts[1:]))
            else:
                skipped[dxftype] = skipped.get(dxftype, 0) + 1

        model.metadata["skipped_entities"] = skipped
        model.metadata["warnings"] = []
        if skipped:
            model.metadata["warnings"].append("Đối tượng chưa nhập: " + ", ".join(f"{k}: {v}" for k, v in sorted(skipped.items())))
        if insunits == 0:
            model.metadata["warnings"].append("Bản vẽ không khai báo đơn vị; đang hiểu 1 đơn vị = 1 mm.")
        if projected_3d:
            model.metadata["warnings"].append("Bản vẽ có cao độ Z; đang phân tích hình chiếu XY, không phải mô hình 3D.")
        return model

    def _explode_lwpolyline(self, entity: DXFGraphic, scale: float, layer: str) -> Tuple[List[LineSegment2D], List[Arc2D]]:
        lines: List[LineSegment2D] = []
        arcs: List[Arc2D] = []
        points = list(entity.get_points(format="xyb"))  # x, y, bulge
        is_closed = bool(entity.closed)
        n = len(points)
        if n < 2:
            return (lines, arcs)

        num_edges = n if is_closed else n - 1
        for i in range(num_edges):
            p1_x, p1_y, bulge = points[i]
            next_idx = (i + 1) % n
            p2_x, p2_y, _ = points[next_idx]

            pt1 = Point2D(p1_x * scale, p1_y * scale)
            pt2 = Point2D(p2_x * scale, p2_y * scale)

            if abs(bulge) < 1e-6:
                # Straight line
                lines.append(LineSegment2D(start=pt1, end=pt2, layer=layer))
            else:
                # Arc from bulge
                arc = self._bulge_to_arc(pt1, pt2, bulge, layer)
                if arc is not None:
                    arcs.append(arc)
                else:
                    lines.append(LineSegment2D(start=pt1, end=pt2, layer=layer))
        return (lines, arcs)

    def _explode_polyline2d(self, entity: DXFGraphic, scale: float, layer: str) -> Tuple[List[LineSegment2D], List[Arc2D]]:
        lines: List[LineSegment2D] = []
        arcs: List[Arc2D] = []
        try:
            vertices = list(entity.vertices)
            is_closed = bool(entity.is_closed)
            n = len(vertices)
            if n < 2:
                return (lines, arcs)
            num_edges = n if is_closed else n - 1
            for i in range(num_edges):
                v1 = vertices[i]
                v2 = vertices[(i + 1) % n]
                p1 = Point2D(v1.dxf.location.x * scale, v1.dxf.location.y * scale)
                p2 = Point2D(v2.dxf.location.x * scale, v2.dxf.location.y * scale)
                bulge = getattr(v1.dxf, "bulge", 0.0)
                if abs(bulge) < 1e-6:
                    lines.append(LineSegment2D(start=p1, end=p2, layer=layer))
                else:
                    arc = self._bulge_to_arc(p1, p2, bulge, layer)
                    if arc:
                        arcs.append(arc)
                    else:
                        lines.append(LineSegment2D(start=p1, end=p2, layer=layer))
        except Exception:
            pass
        return (lines, arcs)

    def _bulge_to_arc(self, p1: Point2D, p2: Point2D, bulge: float, layer: str) -> Optional[Arc2D]:
        """Convert standard DXF bulge to Arc2D."""
        chord_len = p1.distance_to(p2)
        if chord_len < 1e-6:
            return None
        theta = 4.0 * math.atan(bulge)
        radius = abs(chord_len / (2.0 * math.sin(theta * 0.5)))
        # Sagitta
        sagitta = (bulge * chord_len) * 0.5
        # Midpoint of chord
        mx = (p1.x + p2.x) * 0.5
        my = (p1.y + p2.y) * 0.5
        # Unit normal to chord
        dx = (p2.x - p1.x) / chord_len
        dy = (p2.y - p1.y) / chord_len
        nx = -dy
        ny = dx

        # Distance from chord midpoint to circle center
        d = (chord_len * 0.5) / math.tan(theta * 0.5)
        cx = mx + nx * d
        cy = my + ny * d
        center = Point2D(cx, cy)

        ang1 = math.atan2(p1.y - cy, p1.x - cx) % (2 * math.pi)
        ang2 = math.atan2(p2.y - cy, p2.x - cx) % (2 * math.pi)
        is_ccw = bulge > 0

        return Arc2D(
            center=center,
            radius=radius,
            start_angle=ang1,
            end_angle=ang2,
            is_ccw=is_ccw,
            layer=layer
        )

    def _approximate_spline(self, entity: DXFGraphic, scale: float, layer: str) -> List[LineSegment2D]:
        lines: List[LineSegment2D] = []
        try:
            bspline = entity.construction_tool()
            num_pts = max(16, len(entity.control_points) * 8)
            pts = [Point2D(p.x * scale, p.y * scale) for p in bspline.approximate(num_pts)]
            for i in range(len(pts) - 1):
                lines.append(LineSegment2D(start=pts[i], end=pts[i+1], layer=layer))
        except Exception:
            pass
        return lines


class DXFExporter:
    """Exports CADModel2D to standard CNC-ready DXF file with explicit layers and units."""

    LAYER_COLORS = {
        "OUTER_FRAME": 5,      # Blue
        "CNC_CUTOUT": 7,       # White
        "CNC_POCKET": 3,       # Green
        "SYMMETRY_AXIS": 1,    # Red
        "0": 7
    }

    def __init__(self, dxf_version: str = "R2013"):
        self.dxf_version = dxf_version

    def export(self, model: CADModel2D, filepath: str):
        """Write CADModel2D into DXF file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        doc = ezdxf.new(self.dxf_version, setup=True)

        # Enforce millimeter units
        doc.header["$INSUNITS"] = 4
        doc.header["$MEASUREMENT"] = 1

        msp = doc.modelspace()

        # Ensure standard layers exist with appropriate colors
        all_layers = set(model.layers)
        all_layers.update(["OUTER_FRAME", "CNC_CUTOUT", "SYMMETRY_AXIS"])
        for layer_name in all_layers:
            if layer_name not in doc.layers:
                col = self.LAYER_COLORS.get(layer_name, 7)
                doc.layers.add(name=layer_name, color=col)

        # Export LINEs
        for seg in model.lines:
            msp.add_line(
                (seg.start.x, seg.start.y),
                (seg.end.x, seg.end.y),
                dxfattribs={"layer": seg.layer or "0"}
            )

        # Export ARCs
        for arc in model.arcs:
            start_deg = math.degrees(arc.start_angle)
            end_deg = math.degrees(arc.end_angle)
            if not arc.is_ccw:
                start_deg, end_deg = end_deg, start_deg
            msp.add_arc(
                (arc.center.x, arc.center.y),
                arc.radius,
                start_deg,
                end_deg,
                dxfattribs={"layer": arc.layer or "0"}
            )

        # Export CIRCLEs
        for circ in model.circles:
            msp.add_circle(
                (circ.center.x, circ.center.y),
                circ.radius,
                dxfattribs={"layer": circ.layer or "0"}
            )

        doc.saveas(filepath)
