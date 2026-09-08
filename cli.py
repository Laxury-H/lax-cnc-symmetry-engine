"""
Command Line Interface (CLI) for CNC Pattern Symmetry Repair Engine.

Usage examples:
    # 1. Quick analysis of a DXF file:
    .venv\\Scripts\\python cli.py analyze "C:\\Users\\Lax\\Downloads\\No2.dxf"

    # 2. Analyze and generate visual comparison & heatmap image:
    .venv\\Scripts\\python cli.py analyze "C:\\Users\\Lax\\Downloads\\No2.dxf" --plot

    # 3. Analyze and export JSON report:
    .venv\\Scripts\\python cli.py analyze "C:\\Users\\Lax\\Downloads\\No2.dxf" --json report.json

    # 4. Run automated test suite:
    .venv\\Scripts\\python cli.py test
"""

import argparse
import json
import os
import sys
import numpy as np

from src.io.dxf_io import DXFImporter
from src.topology.graph import TopologyGraph
from src.topology.cycle_finder import CycleFinder
from src.symmetry.scorer import SymmetryAnalyzer
from src.spatial.index import PointSpatialIndex


def analyze_file(file_path: str, save_plot: bool = False, plot_path: str = "", json_path: str = ""):
    if not os.path.exists(file_path):
        print(f"[ERROR] Khong tim thay file: {file_path}")
        sys.exit(1)

    print(f"\n{'='*65}")
    print(f"  CNC PATTERN SYMMETRY ENGINE - REPORT")
    print(f"{'='*65}")
    print(f"File: {os.path.abspath(file_path)}")

    # 1. Load CAD model
    importer = DXFImporter(target_unit="mm")
    model = importer.load(file_path)
    bbox = model.bbox

    print(f"Thuc the CAD:     {len(model.lines)} lines, {len(model.arcs)} arcs, {len(model.circles)} circles")
    print(f"Kich thuoc panel: {bbox.width:.2f} mm x {bbox.height:.2f} mm")
    print(f"Toa do goc:       X: [{bbox.min_x:.2f}, {bbox.max_x:.2f}], Y: [{bbox.min_y:.2f}, {bbox.max_y:.2f}]")

    # 2. Analyze topology & symmetry
    analyzer = SymmetryAnalyzer(tolerance=0.20, endpoint_tolerance=0.10)
    result = analyzer.analyze(model)
    prof = result.primary_profile
    axis = result.primary_axis

    print(f"\n--- KET QUA PHAN TICH DOI XUNG ---")
    print(f"Phan loai:          {result.classification}")
    print(f"De xuat hanh dong:  {result.recommended_action}")
    print(f"Truc doi xung:      Goc {axis.angle_degrees:.2f} deg, Di qua diem ({axis.origin.x:.2f}, {axis.origin.y:.2f})")
    print(f"Loai truc:          {'Dung (Vertical)' if axis.is_vertical else 'Nghieng / Tu do'}")
    print(f"Diem doi xung:      {prof.symmetry_score:.2f} / 100")
    print(f"Do tin cay:         {prof.confidence * 100:.1f} %")
    print(f"Sai lech lon nhat:  {prof.max_deviation:.3f} mm")
    print(f"Sai lech RMS:       {prof.rms_deviation:.3f} mm")
    print(f"Sai lech P90:       {prof.p90_deviation:.3f} mm")
    print(f"Ty le diem khop:    {prof.matched_ratio * 100:.1f} %")
    print(f"Tong so closed loop:{result.total_loops}")
    print(f"So cap motif khop:  {len(result.motif_pairs)}")
    print(f"So motif chua khop: {len(result.unpaired_loops)}")

    if result.motif_pairs:
        worst_pair = max(result.motif_pairs, key=lambda p: p.centroid_deviation)
        print(f"Cap motif lech nhat: Tam lech {worst_pair.centroid_deviation:.3f} mm, Chenh lech dien tich {worst_pair.area_diff_ratio * 100:.1f}%")

    print(f"{'='*65}\n")

    # 3. Export JSON if requested
    if json_path:
        out_json_dir = os.path.dirname(os.path.abspath(json_path))
        if out_json_dir:
            os.makedirs(out_json_dir, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
        print(f"[OK] Da xuat bao cao JSON tai: {os.path.abspath(json_path)}")

    # 4. Generate Plot if requested
    if save_plot or plot_path:
        if not plot_path:
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            plot_path = f"{base_name}_analysis.png"
        generate_analysis_plot(model, result, plot_path)
        print(f"[OK] Da xuat anh phan tich & heatmap tai: {os.path.abspath(plot_path)}")


def generate_analysis_plot(model, result, out_path: str):
    """Generate dual-panel visualization: geometry reflection overlay + deviation heatmap."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    axis = result.primary_axis
    prof = result.primary_profile

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # Subplot 1: CAD geometry + reflection overlay
    for line in model.lines:
        ax1.plot([line.start.x, line.end.x], [line.start.y, line.end.y], color="#222222", lw=1.2)
        refl_l = axis.reflect_line(line)
        ax1.plot([refl_l.start.x, refl_l.end.x], [refl_l.start.y, refl_l.end.y],
                 color="#00a8ff", lw=0.8, linestyle="--", alpha=0.6)

    for arc in model.arcs:
        pts = arc.sample_points(24)
        ax1.plot([p.x for p in pts], [p.y for p in pts], color="#222222", lw=1.2)
        refl_arc = axis.reflect_arc(arc)
        r_pts = refl_arc.sample_points(24)
        ax1.plot([p.x for p in r_pts], [p.y for p in r_pts], color="#00a8ff", lw=0.8, linestyle="--", alpha=0.6)

    # Symmetry Axis Line
    bbox = model.bbox
    y_vals = np.linspace(bbox.min_y - 20, bbox.max_y + 20, 100)
    if abs(axis.direction.dy) > 1e-6:
        x_vals = axis.origin.x + (y_vals - axis.origin.y) * (axis.direction.dx / axis.direction.dy)
        ax1.plot(x_vals, y_vals, color="#e84118", lw=2.0, linestyle="-",
                 label=f"Truc doi xung ({axis.angle_degrees:.2f}°, X={axis.origin.x:.2f})")

    ax1.set_title(f"Hinh hoc & Truc doi xung\n(Den: Goc, Xanh lam dut net: Phan chieu qua truc)", fontsize=11)
    ax1.axis("equal")
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(loc="upper right")

    # Subplot 2: Deviation Heatmap
    sampled_pts = model.get_all_sampled_points(num_samples_per_entity=12)
    spatial = PointSpatialIndex(sampled_pts)

    for line in model.lines:
        ax2.plot([line.start.x, line.end.x], [line.start.y, line.end.y], color="#dddddd", lw=0.8, alpha=0.6)

    devs = []
    pts_x, pts_y = [], []
    for pt in sampled_pts:
        rpt = axis.reflect_point(pt)
        _, dist, _ = spatial.nearest(rpt)
        devs.append(dist)
        pts_x.append(pt.x)
        pts_y.append(pt.y)

    devs_arr = np.array(devs)
    vmax = max(4.0, float(np.percentile(devs_arr, 95)))
    scatter = ax2.scatter(pts_x, pts_y, c=devs_arr, cmap="plasma", s=10, vmin=0.0, vmax=vmax)
    cbar = plt.colorbar(scatter, ax=ax2)
    cbar.set_label("Do lech hinh hoc (mm)", fontsize=10)

    ax2.set_title(f"Heatmap do lech doi xung\nMax: {prof.max_deviation:.2f} mm | RMS: {prof.rms_deviation:.2f} mm | Score: {prof.symmetry_score:.1f}/100", fontsize=11)
    ax2.axis("equal")
    ax2.grid(True, linestyle=":", alpha=0.5)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def run_tests():
    import subprocess
    cmd = [sys.executable, "-m", "pytest", "-v"]
    print("Running test suite...")
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="CNC Pattern Symmetry Repair Engine")
    subparsers = parser.add_subparsers(dest="command")

    # analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Phan tich doi xung cua file DXF")
    analyze_parser.add_argument("file", help="Duong dan toi file .dxf")
    analyze_parser.add_argument("--plot", action="store_true", help="Xuat anh heatmap do lech")
    analyze_parser.add_argument("--output-image", default="", help="Duong dan file anh xuat ra")
    analyze_parser.add_argument("--json", default="", help="Xuat bao cao ra file JSON")

    # test command
    test_parser = subparsers.add_parser("test", help="Chay toan bo test suite")

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_file(args.file, save_plot=args.plot, plot_path=args.output_image, json_path=args.json)
    elif args.command == "test":
        run_tests()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
