"""
Unit tests for LWPOLYLINE bulge and chirality normalization under reflection.
Verifies convex/concave preservation and vertex/bulge order mapping.
"""

import math
import pytest
from src.core.primitives import Point2D, Arc2D
from src.core.transform import SymmetryAxis2D
from src.core.polyline_utils import (
    arc_to_bulge,
    bulge_to_arc,
    reflect_polyline_vertices,
    primitives_to_lwpolyline_vertices
)


def test_bulge_to_arc_and_back_roundtrip():
    """Bulge of 1.0 represents a semicircle (180 deg). Should roundtrip accurately."""
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(20.0, 0.0)
    bulge = 1.0 # Semicircle CCW

    arc = bulge_to_arc(p1, p2, bulge)
    assert arc is not None
    assert abs(arc.cx - 10.0) < 1e-4
    assert abs(arc.cy - 0.0) < 1e-4
    assert abs(arc.radius - 10.0) < 1e-4

    b_back = arc_to_bulge(arc.start_point, arc.end_point, arc.center, arc.is_ccw)
    assert abs(b_back - 1.0) < 1e-4


def test_reflect_polyline_vertices_bulge_inversion():
    """
    Reflecting a polyline across a vertical axis with order preserved
    must invert bulge sign so that a left-convex curve stays convex on the right.
    """
    axis = SymmetryAxis2D.vertical(50.0)

    # Vertices: (x, y, bulge)
    vertices = [
        (0.0, 0.0, 0.5),
        (20.0, 0.0, 0.0),
        (20.0, 20.0, 0.0)
    ]

    refl_verts = reflect_polyline_vertices(vertices, axis, reverse_order=False)
    assert len(refl_verts) == 3

    # (0, 0) reflected across x=50 -> (100, 0)
    assert abs(refl_verts[0][0] - 100.0) < 1e-4
    assert abs(refl_verts[0][1] - 0.0) < 1e-4
    # Bulge inverted from 0.5 to -0.5
    assert abs(refl_verts[0][2] - (-0.5)) < 1e-4

    # (20, 0) reflected -> (80, 0)
    assert abs(refl_verts[1][0] - 80.0) < 1e-4
    assert abs(refl_verts[1][1] - 0.0) < 1e-4
    assert abs(refl_verts[1][2] - 0.0) < 1e-4
