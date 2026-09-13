"""Build-time check: convert DXF -> DWG -> geometry using the installed ODA."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ezdxf
from src.io.cad_io import CADImporter, find_oda_converter


def main():
    executable = find_oda_converter()
    if not executable:
        raise RuntimeError("ODA File Converter is missing")
    with tempfile.TemporaryDirectory(prefix="oda_check_") as temporary:
        root = Path(temporary)
        source, output = root / "input", root / "output"
        source.mkdir()
        output.mkdir()
        doc = ezdxf.new("R2013")
        doc.units = 4
        doc.modelspace().add_lwpolyline([(0, 0), (20, 0), (20, 10), (0, 10)], close=True)
        doc.modelspace().add_circle((10, 5), 2)
        doc.saveas(source / "check.dxf")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        else:
            kwargs["env"] = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        result = subprocess.run([executable, str(source), str(output), "ACAD2018", "DWG", "0", "1", "*.dxf"],
                                timeout=120, capture_output=True, **kwargs)
        if result.returncode:
            raise RuntimeError("ODA conversion failed: " + result.stderr.decode("utf-8", errors="replace"))
        model = CADImporter().load(output / "check.dwg")
        if len(model.lines) != 4 or len(model.circles) != 1 or abs(model.bbox.width - 20) > 1e-6:
            raise RuntimeError("DWG roundtrip changed the reference geometry")
        print("ODA DWG runtime verified: 20 x 10 mm, 4 lines, 1 circle")


if __name__ == "__main__":
    main()
