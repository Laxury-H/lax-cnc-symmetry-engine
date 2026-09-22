"""
Unit tests for CAD I/O Backward Compatibility:
Verifies DXF export support for AutoCAD R12 (AC1009), R2000 (AC1015), and R2013 (AC1027).
"""

import os
import pytest
import ezdxf
from src.core.primitives import Point2D, LineSegment2D, Arc2D
from src.io.dxf_io import CADModel2D, DXFExporter


def test_export_dxf_versions(tmp_path):
    """Verifies that R12, R2000, and R2013 export valid DXF files with layers and primitives preserved."""
    lines = [
        LineSegment2D(Point2D(0.0, 0.0), Point2D(50.0, 0.0), layer="CUT"),
        LineSegment2D(Point2D(50.0, 0.0), Point2D(50.0, 50.0), layer="ENGRAVE")
    ]
    arcs = [
        Arc2D(center=Point2D(25.0, 25.0), radius=10.0, start_angle=0.0, end_angle=3.14159, is_ccw=True, layer="POCKET")
    ]
    model = CADModel2D(lines=lines, arcs=arcs, source_file="test_export.dxf")

    versions = [
        ("R12", "AC1009"),
        ("R2000", "AC1015"),
        ("R2013", "AC1027")
    ]

    for v_code, expected_dxfversion in versions:
        out_path = os.path.join(tmp_path, f"pattern_{v_code}.dxf")
        exporter = DXFExporter(dxf_version=v_code)
        exporter.export(model, out_path)

        assert os.path.exists(out_path)
        doc = ezdxf.readfile(out_path)
        assert doc.dxfversion == expected_dxfversion

        msp = doc.modelspace()
        dxf_lines = list(msp.query("LINE"))
        dxf_arcs = list(msp.query("ARC"))

        assert len(dxf_lines) == 2
        assert len(dxf_arcs) == 1

        # Check layer preservation
        line_layers = {l.dxf.layer for l in dxf_lines}
        assert "CUT" in line_layers
        assert "ENGRAVE" in line_layers
        assert dxf_arcs[0].dxf.layer == "POCKET"
