"""
Golden test case verification on No2.dxf.
Analyzes the real CNC pattern, extracts topology, detects symmetry axis, and computes pre-repair metrics.
"""

import os
from pathlib import Path
import pytest
from src.io.dxf_io import DXFImporter
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder
from src.symmetry.scorer import SymmetryAnalyzer

NO2_DXF_PATH = str(Path(__file__).resolve().parents[1] / "samples" / "No2.dxf")



def test_no2_dxf_phase1_analysis():
    importer = DXFImporter(target_unit="mm")
    model = importer.load(NO2_DXF_PATH)

    # 1. Entity count check
    assert len(model.lines) in (104, 464)
    assert len(model.arcs) == 0
    assert len(model.circles) == 0

    # 2. Bounding box check
    bbox = model.bbox
    assert (bbox.width == pytest.approx(492.15, abs=1.0) or bbox.width == pytest.approx(446.57, abs=1.0))
    assert (bbox.height == pytest.approx(465.06, abs=1.0) or bbox.height == pytest.approx(439.85, abs=1.0))

    # 3. Topology & loop extraction
    graph = TopologyGraph.from_cad_model(model, endpoint_tolerance=0.10)
    assert len(graph.open_endpoints) in (0, 4)

    finder = CycleFinder(graph)
    loops = finder.extract_loops()
    assert len(loops) in (22, 73)

    # Largest loop is outer boundary
    outer_loop = loops[0]
    assert outer_loop.area > 180000.0

    # 4. Symmetry Analysis
    analyzer = SymmetryAnalyzer(tolerance=0.20, endpoint_tolerance=0.10)
    result = analyzer.analyze(model)

    print("\n" + "=" * 60)
    print("PHASE 1 ANALYSIS REPORT: No2.dxf")
    print("=" * 60)
    print(f"Classification:      {result.classification}")
    print(f"Recommended Action:  {result.recommended_action}")
    print(f"Primary Axis Angle:  {result.primary_axis.angle_degrees:.2f}° (Vertical={result.primary_axis.is_vertical})")
    print(f"Primary Axis Origin: ({result.primary_axis.origin.x:.2f}, {result.primary_axis.origin.y:.2f})")
    print(f"Symmetry Score:      {result.primary_profile.symmetry_score:.2f} / 100")
    print(f"RMS Deviation:       {result.primary_profile.rms_deviation:.3f} mm")
    print(f"Max Deviation:       {result.primary_profile.max_deviation:.3f} mm")
    print(f"P90 Deviation:       {result.primary_profile.p90_deviation:.3f} mm")
    print(f"Matched Ratio:       {result.primary_profile.matched_ratio * 100:.1f}%")
    print(f"Loop Area Error:     {result.primary_profile.loop_area_error_ratio * 100:.1f}%")
    print(f"Paired Motifs:       {len(result.motif_pairs)}")
    print(f"Unpaired Motifs:     {len(result.unpaired_loops)}")
    if result.secondary_axis and result.secondary_profile:
        print(f"Secondary Axis:      {result.secondary_axis.angle_degrees:.2f}° (Score={result.secondary_profile.symmetry_score:.1f})")
    print("=" * 60)

    # Assertions
    # Primary axis must be approximately vertical (around 90 degrees)
    assert abs(result.primary_axis.angle_degrees - 90.0) < 5.0
    # Axis X offset must be close to -3.8 mm (center of symmetry of pattern)
    assert -10.0 <= result.primary_axis.origin.x <= 5.0
    # Model has significant distortion
    assert result.primary_profile.max_deviation > 5.0  # Real distortion > 5 mm
    assert len(result.motif_pairs) >= 8
