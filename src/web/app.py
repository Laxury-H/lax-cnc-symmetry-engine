"""
Flask Web Application Backend for CNC Pattern Symmetry Repair Engine.
Provides REST API for uploading, analyzing, repairing, and exporting CAD DXF models.
"""

from __future__ import annotations
import os
import uuid
import json
from time import perf_counter
from typing import Dict, Any, Optional, List
from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from src.io.dxf_io import DXFImporter, DXFExporter, CADModel2D
from src.io.cad_io import CADImporter, CADImportError, FORMATS, format_capabilities
from src.symmetry.scorer import SymmetryAnalyzer
from src.repair.engine import PatternRepairEngine
from src.core.transform import SymmetryAxis2D
from src.core.primitives import Point2D, LineSegment2D, BoundingBox2D
from src.web.tasks import TASK_MANAGER

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR)
app.config["MAX_CONTENT_LENGTH"] = 51 * 1024 * 1024
CORS(app)

# In-memory storage for active sessions: {session_id: {"model": CADModel2D, "analysis": ..., "repaired": ...}}
SESSIONS: Dict[str, Dict[str, Any]] = {}


def session_candidates(session, straighten_boundary=True, exclusion_zones=None):
    """Keep only the latest option set; manual edits invalidate this cache."""
    cached = session.get("candidate_cache")
    if cached is not None and cached[0] == straighten_boundary and cached[2] == exclusion_zones:
        return cached[1], True
    from src.repair.candidates import CandidateRepairGenerator
    candidates = CandidateRepairGenerator(straighten_boundary=straighten_boundary).generate_all(
        session["model"], features=session.get("features"), intent=session.get("intent"),
        exclusion_zones=exclusion_zones
    )
    session["candidate_cache"] = (straighten_boundary, candidates, exclusion_zones)
    return candidates, False


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), error.code
    return error


def serialize_model_to_json(model: CADModel2D) -> Dict[str, Any]:
    """Serialize lines and arcs for frontend Canvas rendering."""
    lines_data = []
    for l in model.lines:
        lines_data.append({
            "x1": round(l.start.x, 3), "y1": round(l.start.y, 3),
            "x2": round(l.end.x, 3), "y2": round(l.end.y, 3),
            "layer": l.layer
        })

    arcs_data = []
    for a in model.arcs:
        arcs_data.append({
            "cx": round(a.center.x, 3), "cy": round(a.center.y, 3),
            "radius": round(a.radius, 3),
            "start_ang": round(a.start_angle, 4),
            "end_ang": round(a.end_angle, 4),
            "is_ccw": a.is_ccw,
            "layer": a.layer
        })

    bbox = model.bbox
    for circle in model.circles:
        arcs_data.append({"cx": circle.center.x, "cy": circle.center.y,
                          "radius": circle.radius, "start_ang": 0,
                          "end_ang": 6.283185307179586, "is_ccw": True, "layer": circle.layer})
    return {
        "lines": lines_data,
        "arcs": arcs_data,
        "bbox": {
            "min_x": round(bbox.min_x, 2), "max_x": round(bbox.max_x, 2),
            "min_y": round(bbox.min_y, 2), "max_y": round(bbox.max_y, 2),
            "width": round(bbox.width, 2), "height": round(bbox.height, 2)
        }
    }


@app.route("/")
def serve_index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/favicon.ico")
def serve_favicon():
    return send_from_directory(STATIC_DIR, "favicon.svg", mimetype="image/svg+xml")


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)


@app.route("/api/samples", methods=["GET"])
def list_samples():
    samples = []
    project_sample = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "samples", "No2.dxf"))
    default_no2 = project_sample if os.path.exists(project_sample) else r"C:\Users\Lax\Downloads\No2.dxf"
    if os.path.exists(default_no2):
        samples.append({
            "id": "sample_no2",
            "name": "Mẫu thử CNC",
            "path": default_no2
        })
    return jsonify({"samples": samples})


@app.route("/api/load-sample", methods=["POST"])
def load_sample():
    data = request.json or {}
    sample_id = data.get("sample_id")

    if sample_id == "sample_no2":
        project_sample = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "samples", "No2.dxf"))
        if os.path.exists(project_sample):
            file_path = project_sample
        else:
            file_path = r"C:\Users\Lax\Downloads\No2.dxf"
    else:
        return jsonify({"error": "Unknown sample ID"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": "Sample file not found on disk"}), 404

    return process_and_store_model(file_path, original_filename="No2.dxf")


@app.route("/api/formats", methods=["GET"])
def list_formats():
    return jsonify({"formats": format_capabilities(), "max_file_bytes": 50 * 1024 * 1024,
                    "scope": "Hình học 2D; xuất kết quả DXF"})


@app.route("/api/tasks/<task_id>/progress", methods=["GET"])
def task_progress(task_id: str):
    """Server-Sent Events (SSE) streaming live job progress to client."""
    return Response(TASK_MANAGER.stream_task_progress(task_id), mimetype="text/event-stream")


@app.route("/api/tasks/<task_id>/result", methods=["GET"])
def task_result(task_id: str):
    """Fetch completed task result."""
    task = TASK_MANAGER.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task.status == "completed":
        return jsonify({"status": "completed", "result": task.result})
    if task.status == "failed":
        return jsonify({"status": "failed", "error": task.error}), 500
    return jsonify({"status": task.status, "progress": task.progress, "stage": task.stage})


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    session_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in FORMATS:
        return jsonify({"error": "Định dạng chưa hỗ trợ. Chọn " + ", ".join(FORMATS)}), 400

    saved_path = os.path.join(UPLOAD_DIR, f"{session_id}{ext}")
    file.save(saved_path)

    is_async = request.args.get("async", "").lower() in ("1", "true", "yes")
    if is_async:
        def run_analysis(progress_cb):
            res = process_and_store_model(
                saved_path,
                original_filename=file.filename,
                session_id=session_id,
                progress_callback=progress_cb
            )
            return res.get_json() if hasattr(res, "get_json") else res

        task_id = TASK_MANAGER.submit_task(run_analysis)
        return jsonify({
            "task_id": task_id,
            "session_id": session_id,
            "status": "queued",
            "progress_url": f"/api/tasks/{task_id}/progress",
            "result_url": f"/api/tasks/{task_id}/result"
        })

    response = process_and_store_model(saved_path, original_filename=file.filename, session_id=session_id)
    if session_id not in SESSIONS:
        os.remove(saved_path)
    return response


def process_and_store_model(file_path: str, original_filename: str, session_id: Optional[str] = None, progress_callback: Optional[Any] = None):
    started = perf_counter()
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    try:
        if progress_callback: progress_callback(15, "Đang nạp file bản vẽ và chuẩn hóa đơn vị CAD...")
        importer = CADImporter(target_unit="mm")
        model = importer.load(file_path)

        if progress_callback: progress_callback(40, "Đang phân tích trục đối xứng gương RANSAC...")
        analyzer = SymmetryAnalyzer(tolerance=0.20, endpoint_tolerance=0.10)
        result = analyzer.analyze(model)

        # Compute point deviation heatmap data
        sampled_pts = model.get_all_sampled_points(num_samples_per_entity=10)
        from src.spatial.index import PointSpatialIndex
        spatial = PointSpatialIndex(sampled_pts)

        heatmap_points = []
        for p in sampled_pts:
            rp = result.primary_axis.reflect_point(p)
            _, dist, _ = spatial.nearest(rp)
            heatmap_points.append({"x": round(p.x, 2), "y": round(p.y, 2), "dev": round(dist, 3)})

        if progress_callback: progress_callback(60, "Đang phát hiện đối xứng quay (Cn/Dn) và phân cụm motif...")
        # Rotational Symmetry Detection (C_n, D_n)
        from src.symmetry.rotational import RotationalSymmetryDetector
        rot_detector = RotationalSymmetryDetector(tolerance=0.25)
        rot_profile = rot_detector.detect(sampled_pts, center=result.primary_axis.origin)
        rot_json = rot_profile.to_dict()

        # Spatial Clustering (Local vs Global Motifs)
        from src.symmetry.clustering import SpatialMotifClusterer
        clusterer = SpatialMotifClusterer()
        motif_clusters = clusterer.cluster_model(model)
        clusters_json = [c.to_dict() for c in motif_clusters]

        if progress_callback: progress_callback(80, "Đang phân tích ý đồ thiết kế và chấm điểm chất lượng...")
        from src.features.extractor import FeatureExtractor
        from src.anchors.detector import AnchorDetector
        from src.intent.detector import DesignIntentDetector
        from src.quality.scorer import VisualQualityScorer

        fe = FeatureExtractor()
        features = fe.extract(model)

        vq_scorer = VisualQualityScorer()
        vq_report = vq_scorer.score(model, symm_result=result)

        anchor_det = AnchorDetector()
        anchors = anchor_det.detect_anchors(model)

        intent_det = DesignIntentDetector()
        intent = intent_det.detect_intent(features["lines"], features["loops"], model.bbox)

        anchors_json = [a.to_dict() for a in anchors]
        intent_json = intent.to_dict()
        vq_json = vq_report.to_dict()

        if progress_callback: progress_callback(95, "Lưu trữ phiên làm việc...")
        SESSIONS[session_id] = {
            "original_path": file_path,
            "filename": original_filename,
            "model": model,
            "analysis": result,
            "rotational": rot_profile,
            "clusters": motif_clusters,
            "features": features,
            "anchors": anchors,
            "intent": intent,
            "visual_quality": vq_report,
            "repaired_result": None
        }

        return jsonify({
            "session_id": session_id,
            "filename": original_filename,
            "geometry": serialize_model_to_json(model),
            "import_info": model.metadata,
            "analysis": result.to_dict(),
            "rotational_symmetry": rot_json,
            "motif_clusters": clusters_json,
            "heatmap": heatmap_points,
            "visual_quality": vq_json,
            "anchors": anchors_json,
            "intent": intent_json,
            "elapsed_seconds": round(perf_counter() - started, 3)
        })
    except CADImportError as e:
        return jsonify({"error": str(e)}), e.status_code
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/candidates/<session_id>", methods=["GET"])
def get_candidates(session_id: str):
    if session_id not in SESSIONS:
        return jsonify({"error": "Session not found"}), 404

    session = SESSIONS[session_id]

    try:
        started = perf_counter()
        candidates, cached = session_candidates(session, request.args.get("straighten_boundary", "true") != "false")

        cands_data = []
        for c in candidates:
            c_dict = c.to_dict()
            c_dict["geometry"] = serialize_model_to_json(c.repaired_model)
            cands_data.append(c_dict)

        valid = [c for c in candidates if c.validation.is_valid and
                 c.quality_score.composite_quality >= session["visual_quality"].composite_quality - 0.01]
        best = valid[0] if valid else None
        reason = (f"Đề xuất {best.candidate_id[-1].upper()}: chất lượng {best.quality_score.composite_quality:.1f}/100, "
                  f"mức thay đổi ước lượng {best.change_ratio_percent:.1f}%; đã qua kiểm tra hình học. "
                  "Xem trước để đối chiếu ý đồ thiết kế." if best else
                  "Chưa có phương án hợp lệ cải thiện chất lượng. Hãy kiểm tra hoặc sửa bản gốc.")
        return jsonify({"candidates": cands_data, "recommended_id": best.candidate_id if best else None,
                        "recommendation_reason": reason, "cached": cached,
                        "elapsed_seconds": round(perf_counter() - started, 3)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/update-model", methods=["POST"])
def update_model():
    """Update model with user manual edits (added/deleted lines), re-analyze, and export."""
    data = request.json or {}
    session_id = data.get("session_id")
    lines_data = data.get("lines", [])

    if session_id not in SESSIONS:
        return jsonify({"error": "Session not found"}), 404

    session = SESSIONS[session_id]
    original_filename = session["filename"]

    try:
        lines = []
        for ld in lines_data:
            p1 = Point2D(float(ld["x1"]), float(ld["y1"]))
            p2 = Point2D(float(ld["x2"]), float(ld["y2"]))
            layer = ld.get("layer", "0")
            if p1.distance_to(p2) > 1e-4:
                lines.append(LineSegment2D(start=p1, end=p2, layer=layer))

        orig_model = session["model"]
        updated_model = CADModel2D(
            lines=lines,
            arcs=orig_model.arcs,
            circles=orig_model.circles,
            layers=orig_model.layers,
            source_file=orig_model.source_file,
            units="mm",
            metadata={"manually_edited": True}
        )

        analyzer = SymmetryAnalyzer(tolerance=0.20, endpoint_tolerance=0.10)
        result = analyzer.analyze(updated_model)

        sampled_pts = updated_model.get_all_sampled_points(num_samples_per_entity=10)
        from src.spatial.index import PointSpatialIndex
        spatial = PointSpatialIndex(sampled_pts)

        heatmap_points = []
        for p in sampled_pts:
            rp = result.primary_axis.reflect_point(p)
            _, dist, _ = spatial.nearest(rp)
            heatmap_points.append({"x": round(p.x, 2), "y": round(p.y, 2), "dev": round(dist, 3)})

        from src.features.extractor import FeatureExtractor
        from src.anchors.detector import AnchorDetector
        from src.intent.detector import DesignIntentDetector
        from src.quality.scorer import VisualQualityScorer

        fe = FeatureExtractor()
        features = fe.extract(updated_model)

        vq_scorer = VisualQualityScorer()
        vq_report = vq_scorer.score(updated_model, symm_result=result)

        anchor_det = AnchorDetector()
        anchors = anchor_det.detect_anchors(updated_model)

        intent_det = DesignIntentDetector()
        intent = intent_det.detect_intent(features["lines"], features["loops"], updated_model.bbox)

        # Export manually updated DXF
        base_name = os.path.splitext(original_filename)[0]
        out_filename = f"{session_id}_{base_name}_edited.dxf"
        out_filepath = os.path.join(OUTPUT_DIR, out_filename)
        exporter = DXFExporter(dxf_version="R2013")
        exporter.export(updated_model, out_filepath)
        session["manual_dxf_path"] = out_filepath

        # Update session state
        session["model"] = updated_model
        session["analysis"] = result
        session["features"] = features
        session["anchors"] = anchors
        session["intent"] = intent
        session["visual_quality"] = vq_report
        for key in ("candidate_cache", "repaired_result", "repaired_dxf_path"):
            session.pop(key, None)

        return jsonify({
            "status": "success",
            "session_id": session_id,
            "filename": original_filename,
            "geometry": serialize_model_to_json(updated_model),
            "analysis": result.to_dict(),
            "heatmap": heatmap_points,
            "visual_quality": vq_report.to_dict(),
            "anchors": [a.to_dict() for a in anchors],
            "intent": intent.to_dict(),
            "download_manual_url": f"/api/download-manual/{session_id}",
            "manual_filename": f"{base_name}_edited.dxf"
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-manual/<session_id>", methods=["GET"])
def download_manual(session_id: str):
    if session_id not in SESSIONS:
        return "Session not found", 404

    session = SESSIONS[session_id]
    dxf_path = session.get("manual_dxf_path")
    if not dxf_path or not os.path.exists(dxf_path):
        return "Manual edited file not found", 404

    base_name = os.path.splitext(session["filename"])[0]
    filename = f"{base_name}_edited.dxf"
    response = send_file(
        dxf_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/dxf"
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/repair", methods=["POST"])
def repair_model():
    data = request.json or {}
    session_id = data.get("session_id")
    strategy = data.get("strategy", "canonical_intent")
    candidate_id = data.get("candidate_id")
    straighten_boundary = data.get("straighten_boundary", True)
    dxf_version = data.get("dxf_version", "R2013")
    source_region = data.get("source_region")
    raw_ez = data.get("exclusion_zones", [])
    exclusion_zones = [
        BoundingBox2D(float(z["min_x"]), float(z["min_y"]), float(z["max_x"]), float(z["max_y"]))
        for z in raw_ez if "min_x" in z and "max_x" in z
    ] if raw_ez else None

    if session_id not in SESSIONS:
        return jsonify({"error": "Session not found"}), 404

    session = SESSIONS[session_id]
    orig_model = session["model"]

    try:
        engine = PatternRepairEngine()

        if candidate_id:
            from src.repair.candidates import CandidateRepairGenerator
            generator = CandidateRepairGenerator()
            candidates, _ = session_candidates(session, straighten_boundary, exclusion_zones=exclusion_zones)
            matched = next((c for c in candidates if c.candidate_id == candidate_id), None)
            if matched is None:
                return jsonify({"error": "Không tìm thấy phương án đã chọn."}), 400
            if not matched.validation.is_valid:
                return jsonify({"error": "Phương án không đạt kiểm tra hình học.",
                                "validation": matched.validation.to_dict()}), 422

            pre_symm = session["analysis"]
            analyzer = SymmetryAnalyzer(tolerance=0.20, endpoint_tolerance=0.10)
            post_symm = analyzer.analyze(matched.repaired_model)
            pre_vq = session.get("visual_quality") or generator.quality_scorer.score(orig_model)
            post_vq = matched.quality_score

            from src.repair.engine import RepairResult
            repair_res = RepairResult(
                repaired_model=matched.repaired_model,
                strategy_used=matched.strategy_name.lower(),
                symmetry_score_before=pre_symm.primary_profile.symmetry_score,
                symmetry_score_after=post_symm.primary_profile.symmetry_score,
                max_deviation_before=pre_symm.primary_profile.max_deviation,
                max_deviation_after=post_symm.primary_profile.max_deviation,
                rms_deviation_before=pre_symm.primary_profile.rms_deviation,
                rms_deviation_after=post_symm.primary_profile.rms_deviation,
                is_watertight=matched.validation.is_watertight,
                total_loops_repaired=matched.validation.total_closed_loops,
                operations_log=[
                    f"Applied Candidate {matched.candidate_id.upper()}: {matched.strategy_name}",
                    f"Visual Quality: {post_vq.composite_quality:.2f} / 100",
                    f"Symmetry Score: {post_symm.primary_profile.symmetry_score:.2f} / 100",
                    f"Watertight: {matched.validation.is_watertight}, Duplicates: {matched.validation.duplicate_lines_count}"
                ],
                visual_quality_before=pre_vq.composite_quality,
                visual_quality_after=post_vq.composite_quality,
                spacing_score_before=pre_vq.spacing_score,
                spacing_score_after=post_vq.spacing_score,
                alignment_score_before=pre_vq.alignment_score,
                alignment_score_after=post_vq.alignment_score,
                angle_score_before=pre_vq.angle_score,
                angle_score_after=post_vq.angle_score,
                deformation_before=pre_vq.deformation_penalty,
                deformation_after=post_vq.deformation_penalty,
                verdict=post_vq.verdict,
                candidates=[c.to_dict() for c in candidates]
            )
        else:
            repair_res = engine.repair(
                orig_model,
                strategy=strategy,
                straighten_boundary=straighten_boundary,
                exclusion_zones=exclusion_zones,
                source_region=source_region
            )

        session["repaired_result"] = repair_res

        # Export repaired DXF
        base_name = os.path.splitext(session["filename"])[0]
        out_filename = f"{session_id}_repaired.dxf"
        out_filepath = os.path.join(OUTPUT_DIR, out_filename)
        exporter = DXFExporter(dxf_version=dxf_version)
        exporter.export(repair_res.repaired_model, out_filepath)
        session["repaired_dxf_path"] = out_filepath

        dxf_download_name = f"{base_name}_repaired_{dxf_version.lower()}.dxf"
        report_download_name = f"{base_name}_report.json"

        return jsonify({
            "status": "success",
            "metrics": repair_res.to_dict(),
            "repaired_geometry": serialize_model_to_json(repair_res.repaired_model),
            "download_url": f"/api/download/{session_id}",
            "download_report_url": f"/api/download-report/{session_id}",
            "filename": dxf_download_name,
            "report_filename": report_download_name
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/download/<session_id>", methods=["GET"])
def download_repaired(session_id: str):
    if session_id not in SESSIONS:
        return "Session not found", 404

    session = SESSIONS[session_id]
    dxf_path = session.get("repaired_dxf_path")
    if not dxf_path or not os.path.exists(dxf_path):
        return "Repaired file not found", 404

    base_name = os.path.splitext(session["filename"])[0]
    filename = f"{base_name}_repaired.dxf"
    response = send_file(
        dxf_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/dxf"
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@app.route("/api/download-report/<session_id>", methods=["GET"])
def download_report(session_id: str):
    if session_id not in SESSIONS:
        return "Session not found", 404

    session = SESSIONS[session_id]
    base_name = os.path.splitext(session["filename"])[0]
    filename = f"{base_name}_report.json"

    report_data = {
        "engine": "Lax's CNC SYMMETRY ENGINE",
        "algorithm_version": "2.0 (Design Intent & Geometric Regularization)",
        "file_name": session["filename"],
        "pre_repair_analysis": session["analysis"].to_dict() if session.get("analysis") else None,
        "pre_repair_visual_quality": session["visual_quality"].to_dict() if session.get("visual_quality") else None,
        "design_intent": session["intent"].to_dict() if session.get("intent") else None,
        "anchors": [a.to_dict() for a in session["anchors"]] if session.get("anchors") else None,
        "repair_result": session["repaired_result"].to_dict() if session.get("repaired_result") else None
    }

    report_path = os.path.join(OUTPUT_DIR, f"{session_id}_{base_name}_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    response = send_file(
        report_path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/json"
    )
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def start_server(port: int = None, host: str = None, debug: bool = False):
    if port is None:
        port = int(os.environ.get("PORT", 5000))
    if host is None:
        host = os.environ.get("HOST", "0.0.0.0")
    print(f"\n==================================================")
    print(f"  Lax's CNC SYMMETRY ENGINE - Web Server")
    print(f"  Running on: http://{host}:{port}")
    print(f"==================================================\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    start_server()
