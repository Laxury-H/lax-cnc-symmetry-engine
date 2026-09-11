import io
import importlib
from pathlib import Path

from src.web.app import app, SESSIONS


def test_upload_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(importlib.import_module("src.web.app"), "UPLOAD_DIR", str(tmp_path))
    sample = Path(__file__).resolve().parents[1] / "samples" / "No2.dxf"
    with app.test_client() as client, sample.open("rb") as source:
        response = client.post("/api/upload", data={"file": (source, "../hoa văn.dxf")})
        assert response.status_code == 200
        data = response.get_json()
        try:
            assert data["geometry"]["lines"]
            assert data["analysis"]
            assert data["visual_quality"]
            assert data["filename"] == "../hoa văn.dxf"
            assert Path(SESSIONS[data["session_id"]]["original_path"]).parent == tmp_path
        finally:
            SESSIONS.pop(data["session_id"], None)


def test_upload_invalid_requests():
    with app.test_client() as client:
        assert client.post("/api/upload").status_code == 400
        response = client.post("/api/upload", data={"file": (io.BytesIO(b"bad"), "test.txt")})
        assert response.status_code == 400
        assert response.is_json
        response = client.post("/api/load-sample", data="{", content_type="application/json")
        assert response.status_code == 400
        assert response.is_json
        response = client.get("/api/missing")
        assert response.status_code == 404
        assert response.is_json
