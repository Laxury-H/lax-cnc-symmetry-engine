"""Format dispatch for planar CNC drawings. All coordinates normalize to mm."""
from __future__ import annotations

import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from src.core.primitives import Point2D, LineSegment2D, Arc2D
from src.io.dxf_io import CADModel2D, DXFImporter


FORMATS = {
    ".dxf": "AutoCAD DXF", ".dwg": "AutoCAD DWG (ODA)",
    ".svg": "SVG vector", ".plt": "HPGL", ".hpgl": "HPGL", ".hpg": "HPGL",
    ".nc": "G-code 2D", ".cnc": "G-code 2D", ".gcode": "G-code 2D",
    ".tap": "G-code 2D", ".ngc": "G-code 2D",
}


class CADImportError(ValueError):
    status_code = 422


class ConverterUnavailable(CADImportError):
    status_code = 503


def find_oda_converter():
    """Only trust server configuration and installed executables, never upload data."""
    configured = os.environ.get("ODA_FILE_CONVERTER")
    if configured:
        return str(Path(configured).resolve()) if Path(configured).is_file() else None
    portable = Path(__file__).resolve().parents[2] / ".tools" / "oda" / "runtime" / "ODAFileConverter.exe"
    if os.name == "nt" and portable.is_file():
        return str(portable)
    found = shutil.which("ODAFileConverter")
    if found:
        return found
    from ezdxf.addons import odafc
    configured = odafc.get_win_exec_path() if os.name == "nt" else odafc.get_unix_exec_path()
    if configured and Path(configured).is_file():
        return configured
    if os.name == "nt":
        root = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "ODA"
        for candidate in sorted(root.glob("*/ODAFileConverter.exe"), reverse=True):
            return str(candidate)
    return None


def format_capabilities():
    oda = bool(find_oda_converter())
    return [{"extension": ext, "name": name, "available": ext != ".dwg" or oda,
             "note": "Cần cài ODA File Converter trên máy chủ." if ext == ".dwg" and not oda else ""}
            for ext, name in FORMATS.items()]


def load_dwg(path):
    with path.open("rb") as source:
        signature = source.read(6)
    if not re.fullmatch(rb"AC10\d{2}", signature):
        raise CADImportError("File không có chữ ký DWG hợp lệ; đổi đuôi file không chuyển đổi định dạng.")
    executable = find_oda_converter()
    if not executable:
        raise ConverterUnavailable("Chưa có ODA File Converter trên máy chủ. Cài ODA và đặt ODA_FILE_CONVERTER tới executable, hoặc xuất DXF từ phần mềm CAD.")
    with tempfile.TemporaryDirectory(prefix="cnc_dwg_") as folder:
        root = Path(folder)
        src, dst = root / "input", root / "output"
        src.mkdir()
        dst.mkdir()
        shutil.copyfile(path, src / "drawing.dwg")
        command = [executable, str(src), str(dst), "ACAD2013", "DXF", "0", "1", "drawing.dwg"]
        kwargs = {}
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startup
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["env"] = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        try:
            result = subprocess.run(command, capture_output=True, timeout=120, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise CADImportError("Chuyển DWG quá thời gian 120 giây. Hãy thử bản vẽ nhỏ hơn.") from exc
        except OSError as exc:
            raise ConverterUnavailable("Không khởi chạy được ODA File Converter; kiểm tra cài đặt máy chủ.") from exc
        converted = next(dst.glob("*.[dD][xX][fF]"), None)
        if converted is None:
            raise CADImportError("ODA không chuyển được DWG này. Kiểm tra file hỏng, mã hóa hoặc phiên bản chưa hỗ trợ.")
        model = DXFImporter().load(str(converted))
        model.source_file = str(path)
        model.metadata["converter"] = "ODA File Converter"
        if result.returncode:
            model.metadata.setdefault("warnings", []).append("ODA trả mã lỗi sau khi tạo DXF; cần kiểm tra lại bản vẽ.")
        return model


def add_line(model, a, b, layer="0"):
    if a.distance_to(b) > 1e-9:
        model.lines.append(LineSegment2D(a, b, layer=layer))
        model.layers.add(layer)
    if model.total_entities > 100000:
        raise CADImportError("Bản vẽ vượt giới hạn 100.000 đối tượng hình học.")


def load_svg(path):
    from svgelements import SVG, Shape, Path as SVGPath, Move, Line, Close
    import io
    import xml.etree.ElementTree as ET
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise CADImportError("SVG có khai báo DTD/entity không được hỗ trợ.")
    tree = ET.fromstring(raw)
    if tree.tag.split("}")[-1] != "svg":
        raise CADImportError("Nội dung không phải SVG.")
    unsupported = {"text", "image", "use", "clipPath", "mask", "filter", "style", "script", "foreignObject"}
    for element in tree.iter():
        tag = element.tag.split("}")[-1]
        if tag in unsupported or any(k in element.attrib for k in ("clip-path", "mask", "filter")):
            raise CADImportError(f"SVG chứa {tag} hoặc hiệu ứng chưa hỗ trợ; hãy chuyển text/clone thành path và bỏ mask/clip.")
    svg = SVG.parse(io.BytesIO(raw), reify=True, ppi=96, on_error="raise")
    model = CADModel2D(source_file=str(path), metadata={"warnings": [
        "SVG: quy đổi 96 px/inch, đảo Y sang tọa độ CAD; đường cong được xấp xỉ với bước lấy mẫu tối đa 0,5 mm."
    ]})
    factor = 25.4 / 96
    for element in svg.elements():
        if not isinstance(element, Shape):
            continue
        layer = str(element.id or "SVG")
        for segment in SVGPath(element):
            if isinstance(segment, Move) or segment.start is None or segment.end is None:
                continue
            length = segment.length(error=1e-5) * factor
            if not math.isfinite(length) or length > 50000:
                raise CADImportError("Đường SVG quá lớn hoặc tọa độ không hợp lệ.")
            count = 1 if isinstance(segment, (Line, Close)) else max(8, math.ceil(length / 0.5))
            points = [segment.point(i / count) for i in range(count + 1)]
            for a, b in zip(points, points[1:]):
                add_line(model, Point2D(a.x * factor, -a.y * factor), Point2D(b.x * factor, -b.y * factor), layer)
    return model


def load_hpgl(path):
    text = path.read_text(encoding="utf-8-sig").upper()
    model = CADModel2D(source_file=str(path), metadata={"warnings": ["HPGL: đơn vị plotter 0,025 mm; chỉ nhập nét hạ bút."]})
    current, absolute, pen_down, pen = Point2D(0, 0), True, False, 1
    for instruction in text.split(";"):
        instruction = instruction.strip()
        if not instruction:
            continue
        match = re.fullmatch(r"([A-Z]{2})(.*)", instruction, re.S)
        if not match:
            raise CADImportError("Cú pháp HPGL không hợp lệ.")
        code, args = match.groups()
        if code not in {"IN", "DF", "SP", "PA", "PR", "PU", "PD", "VS", "FS", "PW"}:
            raise CADImportError(f"Lệnh HPGL {code} chưa hỗ trợ; xuất DXF để giữ đủ hình học.")
        try:
            numbers = [float(v) for v in re.split(r"[\s,]+", args.strip()) if v]
        except ValueError as exc:
            raise CADImportError("Tọa độ HPGL không hợp lệ.") from exc
        if not all(math.isfinite(v) for v in numbers):
            raise CADImportError("Tọa độ HPGL không hữu hạn.")
        if code in {"IN", "DF"}:
            absolute, pen_down, pen = True, False, 1
            if code == "IN":
                current = Point2D(0, 0)
        elif code == "SP":
            pen = int(numbers[0]) if numbers else 0
        elif code in {"PA", "PR", "PU", "PD"}:
            if code in {"PA", "PR"}:
                absolute = code == "PA"
            else:
                pen_down = code == "PD"
            if len(numbers) % 2:
                raise CADImportError("HPGL thiếu cặp tọa độ X,Y.")
            for x, y in zip(numbers[::2], numbers[1::2]):
                point = Point2D(x * .025, y * .025)
                if not absolute:
                    point = Point2D(current.x + point.x, current.y + point.y)
                if pen_down and pen:
                    add_line(model, current, point, f"PEN_{pen}")
                current = point
    return model


WORD = re.compile(r"([A-Z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


def load_gcode(path):
    model = CADModel2D(source_file=str(path), metadata={"warnings": [
        "G-code: phân tích hình chiếu XY của G1/G2/G3, bỏ G0; không mô phỏng máy, trạng thái cắt hoặc bù dao. Mặc định mm, G90, tâm cung I/J tương đối và vị trí đầu (0,0,0)."
    ]})
    current = Point2D(0, 0)
    z, scale, absolute, center_absolute, motion = 0., 1., True, False, 0
    for number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = re.sub(r"\([^()]*\)", "", raw).split(";")[0].strip().upper()
        if not line or line == "%":
            continue
        words = WORD.findall(line)
        if WORD.sub("", line).strip() or not words:
            raise CADImportError(f"Dòng {number}: không hỗ trợ macro, biểu thức hoặc cú pháp này.")
        params = {}
        gs, ms = [], []
        for key, value in words:
            value = float(value)
            if not math.isfinite(value):
                raise CADImportError(f"Dòng {number}: số không hữu hạn.")
            if key == "G":
                gs.append(value)
            elif key == "M":
                ms.append(value)
            elif key in "XYZIJRFSTN":
                if key in params:
                    raise CADImportError(f"Dòng {number}: lặp tham số {key}.")
                params[key] = value
            else:
                raise CADImportError(f"Dòng {number}: tham số {key} chưa hỗ trợ.")
        for g in gs:
            if g not in {0, 1, 2, 3, 17, 20, 21, 40, 49, 54, 80, 90, 91, 90.1, 91.1, 94}:
                raise CADImportError(f"Dòng {number}: G{g:g} chưa hỗ trợ (chỉ mặt phẳng XY, không chu trình/bù/offset).")
        if any(m not in {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 30} for m in ms):
            raise CADImportError(f"Dòng {number}: M-code chưa hỗ trợ.")
        for group in ({0, 1, 2, 3, 80}, {20, 21}, {90, 91}, {90.1, 91.1}):
            if sum(g in group for g in gs) > 1:
                raise CADImportError(f"Dòng {number}: nhiều G-code cùng nhóm modal.")
        for g in gs:
            if g in {0, 1, 2, 3, 80}: motion = int(g)
            elif g in {20, 21}: scale = 25.4 if g == 20 else 1.
            elif g in {90, 91}: absolute = g == 90
            elif g in {90.1, 91.1}: center_absolute = g == 90.1
        def coordinate(key, previous):
            return (params[key] * scale + (0 if absolute else previous)) if key in params else previous
        target = Point2D(coordinate("X", current.x), coordinate("Y", current.y))
        target_z = coordinate("Z", z)
        has_motion = any(k in params for k in "XYZIJR")
        if motion not in {2, 3} and any(k in params for k in "IJR"):
            raise CADImportError(f"Dòng {number}: I/J/R chỉ dùng với G2/G3.")
        if has_motion and motion == 80:
            raise CADImportError(f"Dòng {number}: cần G0/G1/G2/G3 sau G80.")
        if has_motion and motion == 1:
            add_line(model, current, target, "FEED_XY")
        elif has_motion and motion in {2, 3}:
            if target_z != z:
                raise CADImportError(f"Dòng {number}: cung xoắn 3D chưa hỗ trợ.")
            ccw = motion == 3
            if "R" in params:
                if "I" in params or "J" in params:
                    raise CADImportError(f"Dòng {number}: không trộn R với I/J.")
                radius = abs(params["R"] * scale)
                chord = current.distance_to(target)
                if chord <= 1e-9 or chord > 2 * radius:
                    raise CADImportError(f"Dòng {number}: bán kính R không hợp lệ.")
                h = math.sqrt(max(0., radius * radius - chord * chord / 4))
                sign = (1 if ccw else -1) * (1 if params["R"] >= 0 else -1)
                center = Point2D((current.x + target.x) / 2 - sign * h * (target.y - current.y) / chord,
                                 (current.y + target.y) / 2 + sign * h * (target.x - current.x) / chord)
            else:
                if not any(k in params for k in "IJ") or (center_absolute and not all(k in params for k in "IJ")):
                    raise CADImportError(f"Dòng {number}: thiếu tâm cung I/J.")
                center = Point2D(params.get("I", 0) * scale + (0 if center_absolute else current.x),
                                 params.get("J", 0) * scale + (0 if center_absolute else current.y))
                radius = center.distance_to(current)
                if radius <= 1e-9 or abs(center.distance_to(target) - radius) > max(.01, radius * 1e-4):
                    raise CADImportError(f"Dòng {number}: tâm cung không khớp điểm cuối.")
            start = math.atan2(current.y - center.y, current.x - center.x)
            end = math.atan2(target.y - center.y, target.x - center.x)
            # Split a full turn to avoid ambiguous equal-angle arcs downstream.
            angles = [start, start + (math.pi if ccw else -math.pi), start] if current.distance_to(target) < 1e-9 else [start, end]
            for a, b in zip(angles, angles[1:]):
                model.arcs.append(Arc2D(center, radius, a, b, is_ccw=ccw, layer="FEED_XY"))
            model.layers.add("FEED_XY")
        current, z = target, target_z
        if 2 in ms or 30 in ms:
            break
    return model


class CADImporter:
    def __init__(self, target_unit="mm"):
        self.target_unit = target_unit

    def load(self, filepath):
        path = Path(filepath)
        ext = path.suffix.lower()
        if ext not in FORMATS:
            raise CADImportError("Định dạng chưa hỗ trợ. Chọn " + ", ".join(FORMATS))
        if path.stat().st_size > 50 * 1024 * 1024:
            raise CADImportError("File vượt giới hạn 50 MB.")
        try:
            if ext == ".dxf": model = DXFImporter().load(str(path))
            elif ext == ".dwg": model = load_dwg(path)
            elif ext == ".svg": model = load_svg(path)
            elif ext in {".plt", ".hpgl", ".hpg"}: model = load_hpgl(path)
            else: model = load_gcode(path)
        except CADImportError:
            raise
        except Exception as exc:
            raise CADImportError(f"Không đọc được {ext.upper()}: file hỏng hoặc chứa dữ liệu chưa hỗ trợ.") from exc
        if not model.total_entities:
            raise CADImportError("File không có đường nét 2D có thể phân tích. Hãy xuất hình học model space thành DXF.")
        if model.total_entities > 100000:
            raise CADImportError("Bản vẽ vượt giới hạn 100.000 đối tượng hình học.")
        for point in model.get_all_sampled_points(2):
            if not all(math.isfinite(v) and abs(v) < 1e9 for v in (point.x, point.y)):
                raise CADImportError("Tọa độ không hợp lệ hoặc vượt giới hạn.")
        model.metadata["source_format"] = ext[1:].upper()
        model.metadata.setdefault("warnings", [])
        return model
