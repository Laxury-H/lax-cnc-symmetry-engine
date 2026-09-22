"""
Unit tests for G1/C1 continuity enforcement at the symmetry axis.
Verifies kink-free mirrored profiles for smooth CNC machining without tool burns.
"""

import math
import pytest
from src.core.primitives import Point2D, LineSegment2D, Arc2D
from src.core.transform import SymmetryAxis2D
from src.core.continuity import AxisContinuityEnforcer


def test_axis_continuity_line_within_threshold():
    """Line segment meeting axis at 88° (2° tilt from perpendicular 90°) should be snapped to exactly 90°."""
    # Vertical axis at x = 50.0
    axis = SymmetryAxis2D.vertical(50.0)
    enforcer = AxisContinuityEnforcer(axis, snap_angle_threshold_deg=5.0)

    # Line from (0, 0) to (50, 1.745) has dy/dx ~ tan(2°) -> angle with axis (90°) is 88° (off by 2°)
    line = LineSegment2D(start=Point2D(0.0, 0.0), end=Point2D(50.0, 1.745))
    adjusted = enforcer.enforce_continuity_line(line)

    # The end point (at the axis) should be shifted or adjusted so tangent is horizontal (dy = 0 at intersection)
    # Start point stays at (0, 0), end point should now be at y = 0.0 (horizontal line perpendicular to vertical axis)
    assert abs(adjusted.end.y - 0.0) < 1e-3
    assert abs(adjusted.end.x - 50.0) < 1e-3
    assert adjusted.is_horizontal


def test_axis_continuity_line_outside_threshold():
    """Line segment meeting axis at 45° (far from 90°) should remain untouched."""
    axis = SymmetryAxis2D.vertical(50.0)
    enforcer = AxisContinuityEnforcer(axis, snap_angle_threshold_deg=5.0)

    line = LineSegment2D(start=Point2D(0.0, 0.0), end=Point2D(50.0, 50.0))
    adjusted = enforcer.enforce_continuity_line(line)

    assert abs(adjusted.end.x - 50.0) < 1e-4
    assert abs(adjusted.end.y - 50.0) < 1e-4


def test_axis_continuity_smooth_mirroring():
    """Line enforced with continuity when mirrored should have 180° collinearity across the axis (0° kink)."""
    axis = SymmetryAxis2D.vertical(100.0)
    enforcer = AxisContinuityEnforcer(axis, snap_angle_threshold_deg=5.0)

    # Slight tilt of 3° at axis
    line = LineSegment2D(start=Point2D(50.0, 10.0), end=Point2D(100.0, 12.618))
    smooth_line = enforcer.enforce_continuity_line(line)

    # Mirrored across vertical axis at x=100
    mirrored_line = axis.reflect_line(smooth_line)

    # Both meet at (100, 10.0)
    assert abs(smooth_line.end.x - mirrored_line.end.x) < 1e-3
    assert abs(smooth_line.end.y - mirrored_line.end.y) < 1e-3

    # Direction vectors should be collinear (dy = 0 for both)
    v1 = smooth_line.direction
    v2 = mirrored_line.direction
    # v1 is (1, 0), v2 is (1, 0)
    assert abs(v1.dy) < 1e-4
    assert abs(v2.dy) < 1e-4
