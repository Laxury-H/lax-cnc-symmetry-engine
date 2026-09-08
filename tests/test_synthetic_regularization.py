"""
Synthetic Test Suite for Geometric Regularization, Intent Detection, and Quality Scoring.
Covers requirements from Section 45 of specification:
  1. Perfect symmetry
  2. Noise & bad angle detection/regularization
  3. Spacing outlier & kerf clustering
  4. Deformation & kink detection ("Móp méo")
  5. Intentional asymmetry preservation
  6. Topology & loop watertightness validation
"""

import math
import pytest
from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.io.dxf_io import CADModel2D
from src.regularization.deformation_detector import DeformationDetector
from src.regularization.angle_regularizer import AngleRegularizer
from src.quality.scorer import VisualQualityScorer
from src.validation.validator import ModelValidator
from src.intent.detector import DesignIntentDetector
from src.features.extractor import FeatureExtractor


def create_rectangle_lines(x1: float, y1: float, x2: float, y2: float) -> list[LineSegment2D]:
    p1 = Point2D(x1, y1)
    p2 = Point2D(x2, y1)
    p3 = Point2D(x2, y2)
    p4 = Point2D(x1, y2)
    return [
        LineSegment2D(p1, p2),
        LineSegment2D(p2, p3),
        LineSegment2D(p3, p4),
        LineSegment2D(p4, p1)
    ]


def test_synthetic_perfect_symmetry():
    """Synthetic Case 1: Perfectly symmetric CNC panel."""
    # Outer frame 500x500
    lines = create_rectangle_lines(0, 0, 500, 500)
    # 4 symmetric corner squares 50x50 at margin 20
    lines.extend(create_rectangle_lines(20, 20, 70, 70))
    lines.extend(create_rectangle_lines(430, 20, 480, 70))
    lines.extend(create_rectangle_lines(430, 430, 480, 480))
    lines.extend(create_rectangle_lines(20, 430, 70, 480))

    model = CADModel2D(lines=lines, arcs=[], circles=[], layers=["0"])
    scorer = VisualQualityScorer()
    vq = scorer.score(model)

    assert vq.symmetry_score >= 99.0
    assert vq.composite_quality >= 95.0
    assert vq.deformation_penalty == 0.0
    assert vq.verdict == "AUTO_ACCEPT"


def test_synthetic_bad_angle_regularization():
    """Synthetic Case 2: Rectangle with slightly tilted lines (89.1° instead of 90°)."""
    # A tilted quad
    pts = [
        Point2D(0, 0),
        Point2D(100, 1.5),    # tilted by ~0.86°
        Point2D(100, 100),
        Point2D(0, 98.5)
    ]

    reg = AngleRegularizer(snap_tolerance_deg=3.0)
    reg_pts = reg.regularize_loop(pts)

    # All angles in regularized loop should be exactly 90°
    p0, p1, p2, p3 = reg_pts
    v01 = p1 - p0
    v12 = p2 - p1
    dot_prod = v01.dx * v12.dx + v01.dy * v12.dy
    assert abs(dot_prod) < 1e-4, "Edges must be strictly orthogonal after regularization"


def test_synthetic_deformation_kink_detection():
    """Synthetic Case 3: Detection of móp méo / kink (e.g. 177.5° near-straight kink)."""
    detector = DeformationDetector(kink_threshold_deg=6.0)

    # A kinked loop where two segments meet at ~177.7° instead of 180°
    p0 = Point2D(0, 0)
    p1 = Point2D(100, 2.0)   # Kink here!
    p2 = Point2D(200, 0)
    p3 = Point2D(200, 100)
    p4 = Point2D(0, 100)
    lines = [
        LineSegment2D(p0, p1),
        LineSegment2D(p1, p2),
        LineSegment2D(p2, p3),
        LineSegment2D(p3, p4),
        LineSegment2D(p4, p0)
    ]
    model = CADModel2D(lines=lines, arcs=[], circles=[], layers=["0"])

    rep = detector.analyze(model)
    assert len(rep.kinks) >= 1, "Must detect sharp kink deformation"
    assert rep.kinks[0].kink_deviation_deg > 0


def test_synthetic_spacing_consistency_clustering():
    """Synthetic Case 4: Detect nominal kerf spacing cluster via median/MAD."""
    detector = DesignIntentDetector()

    # Create parallel slats with spacing 16.5, 16.6, 16.4, and one bad spacing 22.0
    lines = [
        LineSegment2D(Point2D(0, 0), Point2D(100, 0)),
        LineSegment2D(Point2D(0, 16.5), Point2D(100, 16.5)),
        LineSegment2D(Point2D(0, 33.1), Point2D(100, 33.1)), # gap 16.6
        LineSegment2D(Point2D(0, 49.5), Point2D(100, 49.5)), # gap 16.4
        LineSegment2D(Point2D(0, 71.5), Point2D(100, 71.5)), # outlier gap 22.0
    ]

    fe = FeatureExtractor()
    model = CADModel2D(lines=lines, arcs=[], circles=[], layers=["0"])
    features = fe.extract(model)

    intent = detector.detect_intent(features["lines"], features["loops"], model.bbox)
    # Median kerf spacing should cluster around ~16.5
    assert len(intent.nominal_spacings) >= 1
    assert intent.nominal_spacings[0].nominal_spacing_mm == pytest.approx(16.5, abs=0.5)


def test_synthetic_intentional_asymmetry_safety():
    """Synthetic Case 5: Safety Rule - Highly asymmetric design marked as REVIEW, not blindly forced."""
    # Outer frame
    lines = create_rectangle_lines(0, 0, 500, 500)
    # Strongly asymmetric non-centered diagonal features with no counter-part anywhere
    lines.append(LineSegment2D(Point2D(15, 30), Point2D(120, 380)))
    lines.append(LineSegment2D(Point2D(120, 380), Point2D(230, 410)))
    lines.append(LineSegment2D(Point2D(15, 30), Point2D(230, 410)))

    model = CADModel2D(lines=lines, arcs=[], circles=[], layers=["0"])
    scorer = VisualQualityScorer()
    vq = scorer.score(model)

    # Symmetry score must be impacted by large asymmetric triangular motif
    assert vq.symmetry_score < 90.0
    # Should require review rather than auto-accepting destructive symmetry enforcement
    assert vq.verdict in ("REVIEW", "REJECT")


def test_synthetic_watertightness_and_duplicate_cleanup():
    """Synthetic Case 6: Topology validator rejects non-watertight models and counts duplicates."""
    validator = ModelValidator()

    # Open contour (missing 4th side)
    p1 = Point2D(0, 0)
    p2 = Point2D(100, 0)
    p3 = Point2D(100, 100)
    p4 = Point2D(0, 100)
    open_lines = [
        LineSegment2D(p1, p2),
        LineSegment2D(p2, p3),
        LineSegment2D(p3, p4),
        # Duplicate line
        LineSegment2D(p1, p2)
    ]

    model = CADModel2D(lines=open_lines, arcs=[], circles=[], layers=["0"])
    val_res = validator.validate(model, model)

    assert val_res.is_watertight is False, "Open loop must not be marked watertight"
    assert val_res.duplicate_lines_count >= 1, "Duplicate line must be detected"
    assert val_res.is_valid is False
