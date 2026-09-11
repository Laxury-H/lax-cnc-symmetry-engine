# Lax's CNC SYMMETRY ENGINE

[![Render](https://img.shields.io/badge/Render-Deployed-brightgreen?logo=render)](https://render.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Framework-Flask%203.1-black?logo=flask)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Lax's CNC SYMMETRY ENGINE** là giải pháp phần mềm chuyên sâu ứng dụng Computational Geometry (Hình học tính toán), Topology Graph và Design Intent & Geometric Regularization để tự động phát hiện, chẩn đoán sai lệch và nắn chỉnh hoàn hảo các mẫu vách hoa văn CNC thiết kế từ SketchUp (.SKP) và AutoCAD (.DXF).

---

## 🌟 Tính Năng Nổi Bật

- **Design Intent & Geometric Regularization**:
  - Tự động nhận diện ý đồ thiết kế (Góc danh định $0^\circ, 45^\circ, 90^\circ$, cụm khe cắt danh định / Kerf clusters).
  - Khắc phục triệt để hiện tượng gãy gập / móp méo tại các mối ghép trục đối xứng ($174^\circ - 179.7^\circ$).
  - Nắn góc toàn diện (Universal Segment Regularization) triệt tiêu 100% các đường xiên xéo không mong muốn.
  - Bảo toàn tuyệt đối kích thước bao khung bên ngoài và độ kín nước (100% Watertight Loops) phục vụ cắt CNC CAM / Nesting.
- **Đa Phương Án Sửa Đổi (Multi-Hypothesis Candidates)**:
  - So sánh trực quan giữa **Candidate A** (Canonical Intent), **Candidate B** (4-Quadrant Regularized), **Candidate C** (Bilateral L->R) và **Candidate D** (Minimum Change).
- **Bộ Đo Caliper Chuyên Nghiệp (CAD Measuring Tools)**:
  - `A` — Thước đo góc (Angle Caliper): Đo góc chuẩn xác giữa 2 đoạn thẳng bất kỳ.
  - `D` — Thước đo kích thước (Dimension Caliper): Đo khoảng cách milimet giữa 2 điểm mút.
- **Bộ Công Cụ Sửa Thủ Công (Manual CAD Editing)**:
  - `V` — Chọn nét & xem thông số (chiều dài, góc nghiêng, layer).
  - `Delete` — Xóa nét thừa.
  - `L` — Vẽ nét với tính năng bắt điểm (Endpoint Snapping) và khóa góc trực giao (`Shift`-Ortho Lock).
  - `Ctrl+Z` / `Ctrl+Y` — Undo / Redo đa cấp.
  - Đồng bộ và tái chấm điểm thẩm mỹ theo thời gian thực.
- **Giao Diện Web CAD Cao Cấp**:
  - Chế độ Dark Mode hiện đại, bảng điều khiển kính mờ (Glassmorphism), hiển thị tọa độ chuột theo thời gian thực, responsive 100% không bị mất chữ.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Tại Local

Bản nâng cấp giao diện, cách chọn phương án và số đo tốc độ được ghi trong
[UPGRADE_NOTES.md](UPGRADE_NOTES.md). Chạy kiểm thử bằng `python -m pytest -q`
và kiểm tra xử lý phản hồi giao diện bằng `node --test tests/test_api_response.cjs`.

### Yêu cầu hệ thống
- Python 3.11, 3.12 hoặc 3.13
- Git

### Các bước chạy
```bash
# 1. Clone repository
git clone https://github.com/<your-username>/lax-cnc-symmetry-engine.git
cd lax-cnc-symmetry-engine

# 2. Tạo virtual environment và kích hoạt
python -m venv .venv
# Trên Windows:
.venv\Scripts\activate
# Trên Linux/macOS:
source .venv/bin/activate

# 3. Cài đặt thư viện
pip install -r requirements.txt

# 4. Khởi chạy ứng dụng
python server.py
```
Mở trình duyệt và truy cập: `http://localhost:5000`

---

## ☁️ Hướng Dẫn Triển Khai Lên Cloud (Render.com)

`gunicorn.conf.py` đặt một worker (session đang lưu trong RAM) và timeout
300 giây cho các yêu cầu phân tích DXF. Gunicorn tự đọc file này khi chạy
từ thư mục gốc dự án, kể cả với Start Command hiện tại bên dưới.
Sau khi cập nhật mã nguồn, cần deploy lại trên Render. Nếu có cấu hình
`--timeout`, `--workers` hoặc `GUNICORN_CMD_ARGS` riêng, hãy kiểm tra các giá trị
ghi đè. Nếu upload vẫn lỗi HTTP 502/503/504, xem log Render tại thời điểm lỗi:
`WORKER TIMEOUT` cho biết quá thời gian; worker bị `SIGKILL` cần kiểm tra bộ nhớ.
Session sẽ mất khi dịch vụ khởi động lại; cần nạp lại file trong trường hợp đó.

Dự án đã cấu hình sẵn các file `render.yaml` và `Procfile` chuẩn production:

1. Đăng nhập vào [Render.com](https://dashboard.render.com/) bằng tài khoản GitHub.
2. Bấm nút **New +** ở góc trên bên phải -> Chọn **Web Service**.
3. Chọn repository **`lax-cnc-symmetry-engine`** từ danh sách GitHub của bạn.
4. Render sẽ tự động nhận diện cấu hình:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn src.web.app:app --bind 0.0.0.0:$PORT`
   - **Plan**: `Free`
5. Bấm **Deploy Web Service**. Sau 2-3 phút, bạn sẽ nhận được đường dẫn trực tiếp (ví dụ: `https://lax-cnc-symmetry-engine.onrender.com`).

---

## 📂 Cấu Trúc Mã Nguồn

```
├── samples/                # File mẫu kiểm thử (No2.dxf)
├── src/
│   ├── core/               # Các nguyên thủy hình học 2D (Point2D, LineSegment2D, BoundingBox2D)
│   ├── features/           # Trích xuất đặc trưng hình học & điểm neo (Anchors)
│   ├── intent/             # Nhận diện ý đồ thiết kế (Design Intent)
│   ├── io/                 # Đọc & ghi file DXF R2013 (ezdxf)
│   ├── quality/            # Hệ thống chấm điểm Thẩm mỹ (Visual Quality Score 0-100)
│   ├── regularization/     # Thuật toán nắn góc & phục hồi hoa văn
│   ├── repair/             # Bộ máy sửa đối xứng đa phương án (PatternRepairEngine, CandidateRepairGenerator)
│   ├── topology/           # Xây dựng đồ thị tô-pô & dò tìm chu trình kín (TopologyGraph, CycleFinder)
│   ├── validation/         # Kiểm tra tính toàn vẹn (Watertightness, Intersections, Duplicates)
│   └── web/                # Backend Flask API & Giao diện CAD Web (HTML5 Canvas + Vanilla JS)
├── tests/                  # Bộ test kiểm thử tự động & hồi quy
├── Procfile                # Khởi chạy Gunicorn trên Render
├── render.yaml             # Render Blueprint IaC
├── requirements.txt        # Danh sách dependencies
└── server.py               # Launcher khởi chạy local/cloud
```

---

## 📄 Bản Quyền

Phát triển độc quyền cho hệ thống **Lax's CNC SYMMETRY ENGINE**.
Mọi quyền được bảo lưu.
