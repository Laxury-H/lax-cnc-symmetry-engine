"""
Test Suite for Manual Editing & API Synchronization.
Tests adding lines, deleting lines, re-analyzing, and exporting manual DXF files.
"""

import os
import pytest
from src.web.app import app, SESSIONS
from src.io.dxf_io import DXFImporter

NO2_DXF_PATH = r"C:\Users\Lax\Downloads\No2.dxf"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.mark.skipif(not os.path.exists(NO2_DXF_PATH), reason="No2.dxf not present in Downloads")
def test_manual_edit_flow(client):
    # 1. Load sample No2.dxf
    load_resp = client.post("/api/load-sample", json={"sample_id": "sample_no2"})
    assert load_resp.status_code == 200
    data = load_resp.get_json()
    session_id = data["session_id"]
    orig_lines_count = len(data["geometry"]["lines"])
    assert orig_lines_count > 0

    # 2. Simulate User Deleting 1 Line
    edited_lines = list(data["geometry"]["lines"])[1:]
    assert len(edited_lines) == orig_lines_count - 1

    # 3. Simulate User Adding 1 New Line
    edited_lines.append({
        "x1": 0.0,
        "y1": 0.0,
        "x2": 150.0,
        "y2": 0.0,
        "layer": "0"
    })
    assert len(edited_lines) == orig_lines_count

    # 4. Post manual edits to /api/update-model
    update_resp = client.post("/api/update-model", json={
        "session_id": session_id,
        "lines": edited_lines
    })
    assert update_resp.status_code == 200
    up_data = update_resp.get_json()

    assert up_data["status"] == "success"
    assert "visual_quality" in up_data
    assert "analysis" in up_data
    assert "download_manual_url" in up_data
    assert up_data["geometry"]["lines"][-1]["x2"] == 150.0

    # 5. Verify manual DXF export file is generated and readable
    dxf_resp = client.get(up_data["download_manual_url"])
    assert dxf_resp.status_code == 200
    assert len(dxf_resp.data) > 0
