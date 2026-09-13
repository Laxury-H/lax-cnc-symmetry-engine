import io
import math
from pathlib import Path
import subprocess

import ezdxf
import pytest

from src.io import cad_io
from src.io.cad_io import CADImporter, CADImportError, ConverterUnavailable
from src.web.app import app, SESSIONS, serialize_model_to_json


def load_text(tmp_path, extension, text):
    path = tmp_path / ("pattern" + extension)
    path.write_text(text, encoding="utf-8")
    return CADImporter().load(path)


def test_svg_units_transform_and_closed_path(tmp_path):
    model = load_text(tmp_path, ".svg", '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50"><g transform="translate(10,5)"><path d="M0,0h20v10h-20z"/></g></svg>')
    assert len(model.lines) == 4
    assert model.bbox.width == pytest.approx(20, abs=.001)
    assert model.bbox.min_x == pytest.approx(10, abs=.001)
    assert model.bbox.min_y == pytest.approx(-15, abs=.001)


def test_svg_curves(tmp_path):
    model = load_text(tmp_path, ".svg", '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><path d="M0 0 Q50 100 100 0"/></svg>')
    assert len(model.lines) > 8
    assert model.bbox.height == pytest.approx(50 * 25.4 / 96, abs=.02)


@pytest.mark.parametrize("content", ['<svg><text>Hello</text></svg>', '<svg><use href="file:///a"/></svg>', '<!DOCTYPE svg><svg/>', '<svg><path d="bad"/></svg>'])
def test_unsupported_svg(tmp_path, content):
    with pytest.raises(CADImportError):
        load_text(tmp_path, ".svg", content)


def test_hpgl_pen_units_and_relative(tmp_path):
    model = load_text(tmp_path, ".PLT", 'IN;SP1;PU400,800;PD800,800,800,1200;PR;PD-400,0,0,-400;PU5000,5000;')
    assert len(model.lines) == 4
    assert model.bbox.width == pytest.approx(10)
    assert model.bbox.height == pytest.approx(10)
    assert model.bbox.min_x == pytest.approx(10)


@pytest.mark.parametrize("code", ["IN;SC0,100,0,100;", "PD1;", "PDnan,0;"])
def test_hpgl_rejects_unsupported(tmp_path, code):
    with pytest.raises(CADImportError):
        load_text(tmp_path, ".hpgl", code)


def test_gcode_units_relative_modal_rapid_and_end(tmp_path):
    model = load_text(tmp_path, ".nc", "G20 G90\nG0 X1 Y1\nG1 X2 Y1 F100\nG91\nY1\nX-1\nY-1\nM30\nG1 X1000")
    assert len(model.lines) == 4
    assert model.bbox.width == pytest.approx(25.4)
    assert model.bbox.min_x == pytest.approx(25.4)
    assert model.bbox.height == pytest.approx(25.4)


@pytest.mark.parametrize("arc", ["G3 X10 Y0 I5 J0", "G3 X10 Y0 R5", "G2 X10 Y0 R5"])
def test_gcode_arcs(tmp_path, arc):
    model = load_text(tmp_path, ".tap", "G21 G90\n" + arc)
    assert model.arcs[0].radius == pytest.approx(5)
    assert model.arcs[0].center.x == pytest.approx(5)
    assert model.arcs[0].is_ccw == arc.startswith("G3")


def test_gcode_full_circle(tmp_path):
    model = load_text(tmp_path, ".gcode", "G0 X5 Y0\nG3 I-5 J0")
    assert len(model.arcs) == 2
    assert model.bbox.width == pytest.approx(10, abs=.3)


@pytest.mark.parametrize("code", ["G18 G2 X1 Z1 I1", "G53 G0 X0", "G81 X1 Y1 Z-1", "G1 X#1", "G92 X0", "M98 P1", "G2 X10 I1", "G2 X10 R1", "G1 X1 X2", "G90 G91 X1", "G80 X1", "G2 X1 I.5 Z1"])
def test_gcode_rejects_unsupported_instead_of_wrong_geometry(tmp_path, code):
    with pytest.raises(CADImportError):
        load_text(tmp_path, ".cnc", code)


def test_dxf_nested_blocks_ellipse_circle(tmp_path):
    doc = ezdxf.new()
    doc.units = 4
    block = doc.blocks.new("shape")
    block.add_line((0, 0), (10, 0))
    nested = doc.blocks.new("nested")
    nested.add_blockref("shape", (5, 0))
    doc.modelspace().add_blockref("nested", (10, 20), dxfattribs={"rotation": 90})
    doc.modelspace().add_ellipse((0, 0), (10, 0), .5)
    doc.modelspace().add_circle((50, 50), 4)
    doc.modelspace().add_text("not a contour")
    path = tmp_path / "block.dxf"
    doc.saveas(path)
    model = CADImporter().load(path)
    assert model.lines[0].start.x == pytest.approx(10)
    assert model.lines[0].start.y == pytest.approx(25)
    assert model.lines[0].end.y == pytest.approx(35)
    assert len(model.lines) > 10
    assert model.metadata["skipped_entities"] == {"TEXT": 1}
    assert serialize_model_to_json(model)["arcs"][-1]["end_ang"] == pytest.approx(math.tau)


def test_dwg_missing_converter_and_bad_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_io, "find_oda_converter", lambda: None)
    with pytest.raises(ConverterUnavailable):
        load_text(tmp_path, ".dwg", "AC1032dummy")
    with pytest.raises(CADImportError, match="chữ ký"):
        load_text(tmp_path, ".dwg", "not dwg")


def test_dwg_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(cad_io, "find_oda_converter", lambda: "oda")
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 120
        assert args[0][-1] == "drawing.dwg"
        raise subprocess.TimeoutExpired(args[0], 120)
    monkeypatch.setattr(cad_io.subprocess, "run", timeout)
    with pytest.raises(CADImportError, match="120"):
        load_text(tmp_path, ".dwg", "AC1032dummy")


def test_real_oda_roundtrip(tmp_path):
    executable = cad_io.find_oda_converter()
    if not executable:
        pytest.skip("ODA runtime is optional on CI")
    source, destination = tmp_path / "src", tmp_path / "dwg"
    source.mkdir()
    destination.mkdir()
    doc = ezdxf.new("R2013")
    doc.units = 4
    doc.modelspace().add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
    doc.modelspace().add_circle((10, 5), 2)
    doc.saveas(source / "test.dxf")
    kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if cad_io.os.name == "nt" else {"env": dict(cad_io.os.environ, QT_QPA_PLATFORM="offscreen")}
    subprocess.run([executable, str(source), str(destination), "ACAD2018", "DWG", "0", "1", "*.dxf"], timeout=120, capture_output=True, check=True, **kwargs)
    model = CADImporter().load(destination / "test.dwg")
    assert len(model.lines) == 4
    assert len(model.circles) == 1
    assert model.bbox.width == pytest.approx(20)
    assert model.metadata["source_format"] == "DWG"


@pytest.mark.parametrize("extension,content", [
    (".svg", '<svg width="20mm" height="10mm" viewBox="0 0 20 10"><path d="M0 0H20V10H0Z"/></svg>'),
    (".plt", "IN;PU0,0;PD800,0,800,400,0,400,0,0;"),
    (".nc", "G21 G90\nG0 X0 Y0\nG1 X20\nY10\nX0\nY0\nM30")])
def test_upload_new_formats(tmp_path, monkeypatch, extension, content):
    import importlib
    monkeypatch.setattr(importlib.import_module("src.web.app"), "UPLOAD_DIR", str(tmp_path))
    with app.test_client() as client:
        response = client.post("/api/upload", data={"file": (io.BytesIO(content.encode()), "pattern" + extension)})
        assert response.status_code == 200, response.get_json()
        data = response.get_json()
        try:
            assert len(data["geometry"]["lines"]) == 4
            assert data["geometry"]["bbox"]["width"] == pytest.approx(20)
            assert data["import_info"]["source_format"] == extension[1:].upper()
        finally:
            SESSIONS.pop(data["session_id"], None)


def test_failed_upload_cleanup_and_capabilities(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setattr(importlib.import_module("src.web.app"), "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(cad_io, "find_oda_converter", lambda: None)
    with app.test_client() as client:
        formats = client.get("/api/formats").get_json()["formats"]
        assert next(f for f in formats if f["extension"] == ".dwg")["available"] is False
        for name, content, status in [("bad.dxf", b"bad", 422), ("file.dwg", b"AC1032dummy", 503)]:
            response = client.post("/api/upload", data={"file": (io.BytesIO(content), name)})
            assert response.status_code == status
            assert response.is_json
        assert not list(tmp_path.iterdir())
