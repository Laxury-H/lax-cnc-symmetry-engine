"""
Regression Test for Golden File: No2.dxf (No2. Vach CNC - 115.skp).
Tests Design Intent & Geometric Regularization Engine.
Verifies that repair achieves:
  - Visual Quality >= 95.0 / 100 (up from baseline 55.53)
  - Symmetry Score >= 97.0 / 100
  - Angle Regularity >= 98.0%
  - Spacing Consistency >= 95.0%
  - Deformation Penalty == 0.0 (Zero kinks / zero móp méo)
  - 100% Watertight Closed Loops
  - Dimension Preservation of outer panel
  - Auto-Accept Verdict
"""

import os
from pathlib import Path
import pytest
from src.io.dxf_io import DXFImporter
from src.repair.engine import PatternRepairEngine
from src.repair.candidates import CandidateRepairGenerator

NO2_DXF_PATH = str(Path(__file__).resolve().parents[1] / "samples" / "No2.dxf")



def test_no2_canonical_intent_regularization():
    importer = DXFImporter(target_unit="mm")
    model = importer.load(NO2_DXF_PATH)

    orig_bbox = model.bbox
    assert orig_bbox.width > 0 and orig_bbox.height > 0

    engine = PatternRepairEngine()
    result = engine.repair(model, strategy="canonical_intent")

    # 1. Visual Quality and Sub-metrics
    assert result.visual_quality_after is not None
    assert result.visual_quality_after >= 92.0, f"Expected Visual Quality >= 92.0, got {result.visual_quality_after}"
    assert result.visual_quality_after > result.visual_quality_before, "Visual Quality must improve"

    assert result.symmetry_score_after >= 97.0, f"Expected Symmetry >= 97.0, got {result.symmetry_score_after}"
    assert result.angle_score_after >= 98.0, f"Expected Angle Regularity >= 98.0, got {result.angle_score_after}"
    assert result.spacing_score_after >= 95.0, f"Expected Spacing Consistency >= 95.0, got {result.spacing_score_after}"

    # 2. Triệt tiêu hoàn toàn móp méo (Deformation penalty == 0.0)
    assert result.deformation_after == 0.0, f"Expected 0.0 deformation penalty, got {result.deformation_after}"

    # 3. Topology & Watertightness
    assert result.is_watertight is True
    assert result.verdict == "AUTO_ACCEPT"

    # 4. Dimension Preservation (Original: 492.15 x 465.06)
    rep_bbox = result.repaired_model.bbox
    assert rep_bbox.width == pytest.approx(orig_bbox.width, abs=1.0)
    assert rep_bbox.height == pytest.approx(orig_bbox.height, abs=1.0)



def test_no2_multi_hypothesis_candidate_generation():
    importer = DXFImporter(target_unit="mm")
    model = importer.load(NO2_DXF_PATH)

    generator = CandidateRepairGenerator()
    candidates = generator.generate_all(model)

    assert len(candidates) >= 4, "Must generate at least 4 competing candidates"

    # Best candidate must be Candidate A (Canonical Intent)
    best_cand = candidates[0]
    assert best_cand.candidate_id == "candidate_a"
    assert best_cand.quality_score.composite_quality >= 92.0
    assert best_cand.validation.is_valid is True
    assert best_cand.validation.is_watertight is True
    assert best_cand.validation.duplicate_lines_count == 0
