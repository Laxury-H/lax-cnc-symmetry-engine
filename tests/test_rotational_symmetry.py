"""
Unit tests for Rotational and Cyclic Symmetry Detection (Cn, Dn).
Verifies detection of rosette, medallion, and fan patterns common in CNC art.
"""

import math
import pytest
from src.core.primitives import Point2D, LineSegment2D
from src.io.dxf_io import CADModel2D
from src.symmetry.rotational import RotationalSymmetryDetector


def create_rotational_pattern(order: int, has_reflection: bool = False) -> CADModel2D:
    """Helper to generate an exact Cn or Dn symmetric model."""
    lines = []
    base_petal = [
        (Point2D(10, 0), Point2D(30, 10)),
        (Point2D(30, 10), Point2D(40, 0)),
        (Point2D(40, 0), Point2D(10, 0))
    ]

    for k in range(order):
        ang = (2.0 * math.pi * k) / order
        cos_a = math.cos(ang)
        sin_a = math.sin(ang)

        for p1, p2 in base_petal:
            rp1 = Point2D(p1.x * cos_a - p1.y * sin_a, p1.x * sin_a + p1.y * cos_a)
            rp2 = Point2D(p2.x * cos_a - p2.y * sin_a, p2.x * sin_a + p2.y * cos_a)
            lines.append(LineSegment2D(rp1, rp2))

            if has_reflection:
                # Mirror across x-axis then rotate
                mp1 = Point2D(p1.x * cos_a - (-p1.y) * sin_a, p1.x * sin_a + (-p1.y) * cos_a)
                mp2 = Point2D(p2.x * cos_a - (-p2.y) * sin_a, p2.x * sin_a + (-p2.y) * cos_a)
                lines.append(LineSegment2D(mp1, mp2))

    return CADModel2D(lines=lines, source_file="test_rotational.dxf")


def test_detect_c4_rotational_symmetry():
    """Detects 4-fold cyclic rotational symmetry C4."""
    model = create_rotational_pattern(order=4, has_reflection=False)
    detector = RotationalSymmetryDetector()
    results = detector.detect(model)

    assert len(results) > 0
    top = results[0]
    assert top.order == 4
    assert top.group in ("C4", "D4")
    assert top.confidence > 0.85


def test_detect_c6_d6_symmetry():
    """Detects 6-fold dihedral symmetry D6."""
    model = create_rotational_pattern(order=6, has_reflection=True)
    detector = RotationalSymmetryDetector()
    results = detector.detect(model)

    assert len(results) > 0
    top = results[0]
    assert top.order == 6
    assert top.has_reflection is True
    assert top.group == "D6"
    assert top.confidence > 0.85
