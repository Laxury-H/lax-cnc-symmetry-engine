"""Unit tests for symmetry transformations and reflection."""

import math
import pytest
from src.core.primitives import Point2D, Vector2D, LineSegment2D, Arc2D, Circle2D
from src.core.transform import SymmetryAxis2D, AffineTransform2D


def test_vertical_axis_reflection():
    # Axis at x = 100
    axis = SymmetryAxis2D.vertical(100.0)
    assert axis.is_vertical
    assert not axis.is_horizontal

    p = Point2D(80.0, 50.0)
    refl = axis.reflect_point(p)
    assert refl.x == pytest.approx(120.0)
    assert refl.y == pytest.approx(50.0)

    # Point on axis reflects to itself
    on_axis = Point2D(100.0, 25.0)
    assert axis.reflect_point(on_axis).is_close(on_axis)


def test_horizontal_axis_reflection():
    # Axis at y = 50
    axis = SymmetryAxis2D.horizontal(50.0)
    assert axis.is_horizontal
    assert not axis.is_vertical

    p = Point2D(30.0, 40.0)
    refl = axis.reflect_point(p)
    assert refl.x == pytest.approx(30.0)
    assert refl.y == pytest.approx(60.0)


def test_diagonal_axis_reflection():
    # Line y = x (passing through origin at 45 degrees)
    axis = SymmetryAxis2D.from_angle_and_point(Point2D(0.0, 0.0), math.pi * 0.25)
    p = Point2D(10.0, 30.0)
    refl = axis.reflect_point(p)
    # y = x reflection swaps x and y
    assert refl.x == pytest.approx(30.0)
    assert refl.y == pytest.approx(10.0)


def test_line_reflection():
    axis = SymmetryAxis2D.vertical(0.0)
    line = LineSegment2D(start=Point2D(-20.0, 10.0), end=Point2D(-10.0, 40.0))
    refl_line = axis.reflect_line(line)
    assert refl_line.start.x == pytest.approx(20.0)
    assert refl_line.start.y == pytest.approx(10.0)
    assert refl_line.end.x == pytest.approx(10.0)
    assert refl_line.end.y == pytest.approx(40.0)
    assert refl_line.length == pytest.approx(line.length)


def test_affine_transform():
    t = AffineTransform2D.translation(10.0, 20.0)
    p = Point2D(5.0, 5.0)
    res = t.apply_point(p)
    assert res.x == pytest.approx(15.0)
    assert res.y == pytest.approx(25.0)

    rot = AffineTransform2D.rotation(math.pi * 0.5)  # 90 deg CCW
    res_rot = rot.apply_point(Point2D(1.0, 0.0))
    assert res_rot.x == pytest.approx(0.0, abs=1e-6)
    assert res_rot.y == pytest.approx(1.0)
