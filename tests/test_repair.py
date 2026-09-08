"""Unit tests for Phase 2 Repair Engine."""

import os
import pytest
from src.io.dxf_io import DXFImporter
from src.repair.engine import PatternRepairEngine

NO2_DXF_PATH = r"C:\Users\Lax\Downloads\No2.dxf"


@pytest.mark.skipif(not os.path.exists(NO2_DXF_PATH), reason="No2.dxf not present in Downloads")
def test_repair_no2_4_quadrant():
    importer = DXFImporter()
    model = importer.load(NO2_DXF_PATH)

    engine = PatternRepairEngine()
    result = engine.repair(model, strategy="4_quadrant", straighten_boundary=True)

    assert result.symmetry_score_after == pytest.approx(100.0, abs=0.01)
    assert result.max_deviation_after < 1e-4
    assert result.rms_deviation_after < 1e-4
    assert result.is_watertight
    assert result.total_loops_repaired in (22, 73, 452)


@pytest.mark.skipif(not os.path.exists(NO2_DXF_PATH), reason="No2.dxf not present in Downloads")
def test_repair_no2_mirror_left_to_right():
    importer = DXFImporter()
    model = importer.load(NO2_DXF_PATH)

    engine = PatternRepairEngine()
    result = engine.repair(model, strategy="mirror_left_to_right", straighten_boundary=True)

    assert result.symmetry_score_after == pytest.approx(100.0, abs=0.01)
    assert result.max_deviation_after < 1e-4
    assert result.rms_deviation_after < 1e-4
    assert result.is_watertight


@pytest.mark.skipif(not os.path.exists(NO2_DXF_PATH), reason="No2.dxf not present in Downloads")
def test_repair_no2_mirror_bottom_to_top():
    importer = DXFImporter()
    model = importer.load(NO2_DXF_PATH)

    engine = PatternRepairEngine()
    result = engine.repair(model, strategy="mirror_bottom_to_top", straighten_boundary=True)

    assert result.symmetry_score_after == pytest.approx(100.0, abs=0.01)
    assert result.max_deviation_after < 1e-4
    assert result.rms_deviation_after < 1e-4
    assert result.is_watertight
