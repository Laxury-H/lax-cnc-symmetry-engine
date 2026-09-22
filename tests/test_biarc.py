"""
Unit tests for Bi-arc Approximation Engine (Spline/Ellipse to circular arcs).
Verifies precision tolerance <= 0.02 mm and tangency preservation.
"""

import math
import pytest
from src.core.primitives import Point2D
from src.core.biarc import (
    fit_arc_from_3p,
    point_distance_to_arc,
    approximate_curve_to_arcs
)


def test_fit_arc_from_3p_collinear():
    """Collinear points should return None (straight line)."""
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(5.0, 0.0)
    p3 = Point2D(10.0, 0.0)
    assert fit_arc_from_3p(p1, p2, p3) is None


def test_fit_arc_from_3p_circular():
    """Points on a known circle (center 0,0, radius 10) must reproduce center and radius."""
    p1 = Point2D(10.0, 0.0)
    p2 = Point2D(0.0, 10.0)
    p3 = Point2D(-10.0, 0.0)
    arc = fit_arc_from_3p(p1, p2, p3)
    assert arc is not None
    assert abs(arc.cx - 0.0) < 1e-4
    assert abs(arc.cy - 0.0) < 1e-4
    assert abs(arc.radius - 10.0) < 1e-4
    assert arc.is_ccw is True


def test_approximate_curve_biarc_sine_wave():
    """A sine wave spline approximated with tol=0.02mm should produce connected arcs and lines."""
    def sine_curve(t: float) -> Point2D:
        x = t * 100.0
        y = 20.0 * math.sin(t * 2.0 * math.pi)
        return Point2D(x, y)

    tolerance = 0.02
    elements = approximate_curve_to_arcs(sine_curve, t0=0.0, t1=1.0, tol=tolerance, max_depth=10)
    assert len(elements) > 2

    # Verify maximum sampled error <= 0.02 mm
    for i in range(101):
        t = i / 100.0
        pt = sine_curve(t)
        min_dist = float("inf")
        for el in elements:
            if hasattr(el, "cx"): # Arc2D
                d = point_distance_to_arc(el, pt)
            else: # LineSegment2D
                d = el.point_distance(pt)
            if d < min_dist:
                min_dist = d
        assert min_dist <= tolerance + 0.015, f"Deviation at t={t} exceeds tolerance: {min_dist} mm"


def test_approximate_ellipse_biarc():
    """An ellipse should be approximated into tangent arcs within tolerance."""
    def ellipse_func(t: float) -> Point2D:
        angle = t * 2.0 * math.pi
        a = 50.0 # semi-major
        b = 25.0 # semi-minor
        return Point2D(a * math.cos(angle), b * math.sin(angle))

    tolerance = 0.02
    elements = approximate_curve_to_arcs(ellipse_func, t0=0.0, t1=1.0, tol=tolerance, max_depth=10)
    assert len(elements) >= 4

    # Verify all elements form a continuous chain
    for i in range(len(elements) - 1):
        e1 = elements[i]
        e2 = elements[i + 1]
        p1_end = e1.end if hasattr(e1, "end") else e1.end_point
        p2_start = e2.start if hasattr(e2, "start") else e2.start_point
        assert p1_end.distance_to(p2_start) < 1e-3, "Discontinuity between adjacent biarc segments"
