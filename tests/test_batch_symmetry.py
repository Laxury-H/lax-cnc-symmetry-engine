import math
import numpy as np
import pytest

from src.core.primitives import Point2D, LineSegment2D
from src.core.transform import SymmetryAxis2D
from src.spatial.index import PointSpatialIndex
from src.symmetry.error_metrics import SymmetryEvaluator
from src.repair.candidates import CandidateRepairGenerator
from src.io.dxf_io import CADModel2D


@pytest.mark.parametrize('angle', [0, math.pi / 2, .237, 2.8])
def test_batch_matches_scalar_reflection_and_nearest(angle):
    coords = np.random.default_rng(23).normal(size=(600, 2)) * 100
    points = [Point2D(*p) for p in coords]
    axis = SymmetryAxis2D.from_angle_and_point(Point2D(17, -31), angle)
    scalar = np.array([[axis.reflect_point(p).x, axis.reflect_point(p).y] for p in points])
    np.testing.assert_allclose(axis.reflect_coordinates(coords), scalar, atol=1e-12)
    index = PointSpatialIndex(points)
    expected = np.array([index.nearest(axis.reflect_point(p))[1] for p in points])
    evaluator = SymmetryEvaluator(points)
    np.testing.assert_allclose(evaluator.deviations(axis), expected, atol=1e-12)
    profile = evaluator.evaluate(axis)
    assert profile.rms_deviation == pytest.approx(np.sqrt(np.mean(expected ** 2)))
    assert profile.matched_ratio == np.count_nonzero(expected <= .2) / len(points)


def test_empty_batch():
    distances, indices = PointSpatialIndex([]).nearest_batch([[1, 2]])
    assert np.isinf(distances[0]) and indices[0] == -1
    assert SymmetryEvaluator([]).evaluate(SymmetryAxis2D.vertical(0)).sample_count == 0


def test_change_estimate_is_order_independent_and_detects_removed_geometry():
    lines = [LineSegment2D(Point2D(i, 0), Point2D(i, 2)) for i in range(100)]
    model = CADModel2D(lines=lines)
    generator = CandidateRepairGenerator()
    assert generator._compute_change_ratio(model, CADModel2D(lines=list(reversed(lines)))) == 0
    assert generator._compute_change_ratio(model, CADModel2D(lines=[])) == 100
    assert generator._compute_change_ratio(model, CADModel2D(lines=lines[:50])) > 0
