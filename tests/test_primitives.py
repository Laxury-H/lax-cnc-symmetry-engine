"""Unit tests for 2D geometry primitives."""

import math
import pytest
from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D, BoundingBox2D


def test_point2d_operations():
    p1 = Point2D(10.0, 20.0)
    p2 = Point2D(13.0, 24.0)
    assert p1.distance_to(p2) == pytest.approx(5.0)
    assert p1.distance_sq(p2) == pytest.approx(25.0)
    assert p1.is_close(Point2D(10.00001, 20.00001), tol=1e-4)

    v = p2 - p1
    assert isinstance(v, Vector2D)
    assert v.dx == pytest.approx(3.0)
    assert v.dy == pytest.approx(4.0)

    p3 = p1 + v
    assert p3.x == pytest.approx(13.0)
    assert p3.y == pytest.approx(24.0)


def test_vector2d_properties():
    v = Vector2D(3.0, 4.0)
    assert v.length == pytest.approx(5.0)
    u = v.normalized()
    assert u.length == pytest.approx(1.0)
    assert u.dx == pytest.approx(0.6)
    assert u.dy == pytest.approx(0.8)

    perp = v.perpendicular()
    assert perp.dot(v) == pytest.approx(0.0)

    v2 = Vector2D(-4.0, 3.0)
    assert v.dot(v2) == pytest.approx(0.0)
    assert v.angle_with(v2) == pytest.approx(math.pi * 0.5)


def test_line_segment():
    p1 = Point2D(0.0, 0.0)
    p2 = Point2D(100.0, 0.0)
    seg = LineSegment2D(start=p1, end=p2)
    assert seg.length == pytest.approx(100.0)
    assert seg.midpoint == Point2D(50.0, 0.0)
    assert seg.distance_to_point(Point2D(50.0, 10.0)) == pytest.approx(10.0)
    assert seg.distance_to_point(Point2D(-10.0, 0.0)) == pytest.approx(10.0)

    pts = seg.sample_points(5)
    assert len(pts) == 5
    assert pts[0] == Point2D(0.0, 0.0)
    assert pts[-1] == Point2D(100.0, 0.0)


def test_arc_properties():
    center = Point2D(50.0, 50.0)
    radius = 20.0
    arc = Arc2D(center=center, radius=radius, start_angle=0.0, end_angle=math.pi * 0.5, is_ccw=True)
    assert arc.sweep_angle == pytest.approx(math.pi * 0.5)
    assert arc.length == pytest.approx(20.0 * math.pi * 0.5)
    assert arc.start_point.x == pytest.approx(70.0)
    assert arc.start_point.y == pytest.approx(50.0)
    assert arc.end_point.x == pytest.approx(50.0)
    assert arc.end_point.y == pytest.approx(70.0)


def test_bounding_box():
    pts = [Point2D(-10, -20), Point2D(30, 40), Point2D(5, 5)]
    bbox = BoundingBox2D.from_points(pts)
    assert bbox.min_x == -10
    assert bbox.max_x == 30
    assert bbox.width == 40
    assert bbox.height == 60
    assert bbox.center == Point2D(10, 10)
    assert bbox.contains_point(Point2D(0, 0))
    assert not bbox.contains_point(Point2D(50, 50))
