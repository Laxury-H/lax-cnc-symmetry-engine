"""
Unit tests for CNC Toolpath Readiness:
- Micro-gap healing and vertex welding (0.01 - 0.05 mm)
- Intentional tab/micro-joint protection (0.5 - 2.0 mm)
- Winding order normalization (Outer boundary CCW, inner cavities CW)
"""

import pytest
from src.core.primitives import Point2D, LineSegment2D
from src.io.dxf_io import CADModel2D
from src.topology.healing import TopologyHealer
from src.topology.winding import WindingNormalizer


def test_micro_gap_closure_welding():
    """Micro-gaps of 0.02 mm should be welded closed into a continuous loop."""
    # A square with a 0.02mm gap between line 4 and line 1
    lines = [
        LineSegment2D(Point2D(0.0, 0.0), Point2D(100.0, 0.0)),
        LineSegment2D(Point2D(100.0, 0.0), Point2D(100.0, 100.0)),
        LineSegment2D(Point2D(100.0, 100.0), Point2D(0.0, 100.0)),
        LineSegment2D(Point2D(0.0, 100.0), Point2D(0.0, 0.02))  # 0.02 mm gap to (0,0)
    ]
    model = CADModel2D(lines=lines, source_file="test_gap.dxf")

    healer = TopologyHealer(snap_radius=0.05, preserve_tabs=True)
    healed = healer.heal_and_stitch(model)

    # The end of the 4th line should now match (0,0)
    assert healed.lines[3].end.distance_to(healed.lines[0].start) < 1e-4


def test_tab_protection_preserves_gap():
    """An intentional machining tab of 1.2 mm should NOT be welded closed."""
    # A square with an intentional tab opening of 1.2 mm
    lines = [
        LineSegment2D(Point2D(0.0, 0.0), Point2D(100.0, 0.0)),
        LineSegment2D(Point2D(100.0, 0.0), Point2D(100.0, 100.0)),
        LineSegment2D(Point2D(100.0, 100.0), Point2D(0.0, 100.0)),
        LineSegment2D(Point2D(0.0, 100.0), Point2D(0.0, 1.2))  # 1.2 mm intentional tab
    ]
    model = CADModel2D(lines=lines, source_file="test_tab.dxf")

    healer = TopologyHealer(snap_radius=0.05, preserve_tabs=True)
    healed = healer.heal_and_stitch(model)

    # Gap of 1.2 mm should remain intact
    gap = healed.lines[3].end.distance_to(healed.lines[0].start)
    assert abs(gap - 1.2) < 1e-3


def test_winding_order_outer_ccw_inner_cw():
    """
    Outer boundary must be oriented Counter-Clockwise (CCW).
    Inner hole/cavity must be oriented Clockwise (CW).
    """
    # Outer box: CW initially: (0,0) -> (0,100) -> (100,100) -> (100,0)
    outer_cw = [
        Point2D(0.0, 0.0),
        Point2D(0.0, 100.0),
        Point2D(100.0, 100.0),
        Point2D(100.0, 0.0)
    ]
    # Inner hole: CCW initially: (20,20) -> (80,20) -> (80,80) -> (20,80)
    inner_ccw = [
        Point2D(20.0, 20.0),
        Point2D(80.0, 20.0),
        Point2D(80.0, 80.0),
        Point2D(20.0, 80.0)
    ]

    normalizer = WindingNormalizer()
    norm_loops = normalizer.normalize_loops([outer_cw, inner_ccw])

    assert len(norm_loops) == 2

    # Outer loop should now be CCW
    assert normalizer.is_ccw(norm_loops[0]) is True

    # Inner loop should now be CW
    assert normalizer.is_ccw(norm_loops[1]) is False
