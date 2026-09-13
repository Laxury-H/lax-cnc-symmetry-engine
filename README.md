# Lax's CNC SYMMETRY ENGINE

[![Render](https://img.shields.io/badge/Render-Deployed-brightgreen?logo=render)](https://render.com)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Framework-Flask%203.1-black?logo=flask)](https://flask.palletsprojects.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Lax's CNC SYMMETRY ENGINE** phân tích và chỉnh đối xứng hoa văn CNC 2D từ DXF, DWG (qua ODA), SVG, HPGL/PLT và G-code XY. File SketchUp cần xuất DXF trước khi nhập.

### Định dạng nhập

| File | Phạm vi hiện có |
| --- | --- |
| `.dxf` | Model space: line, arc, circle, polyline/bulge, spline, ellipse, block lồng nhau; chuẩn hóa đơn vị mm |
| `.dwg` | Chuyển bằng ODA File Converter rồi dùng cùng bộ đọc DXF; cần runtime trên máy chạy backend |
| `.svg` | Path, line, rect, circle, ellipse, polygon; transform/viewBox và đơn vị 96 dpi; cong xấp xỉ theo bước tối đa 0,5 mm |
| `.plt`, `.hpgl`, `.hpg` | HPGL IN/DF/SP/PA/PR/PU/PD, nét hạ bút, tọa độ tuyệt đối/tương đối, 0,025 mm/đơn vị |
| `.nc`, `.cnc`, `.gcode`, `.tap`, `.ngc` | Hình chiếu XY G1/G2/G3, cung I/J hoặc R, G20/G21, G90/G91, G90.1/G91.1; bỏ rapid G0 |

Giới hạn 50 MB/file, 100.000 đối tượng sau nhập. G-code mặc định mm,
tọa độ tuyệt đối, tâm cung tương đối, vị trí ban đầu (0,0,0); không phải trình
mô phỏng máy và không xác định vật liệu bị cắt theo Z/spindle. Macro, chu trình,
bù dao, G53/G92, mặt phẳng khác XY và cung xoắn bị từ chối. SVG text/clone cần
chuyển thành path; mask/clip/CSS/ảnh raster chưa hỗ trợ. HPGL có lệnh hình học
khác danh sách trên phải xuất DXF. Không đọc trực tiếp SKP, STEP/IGES, STL,
PDF, AI, CDR hoặc mọi phương ngữ điều khiển CNC. Kết quả sửa xuất **DXF**.
Các đối tượng CAD chưa đọc được được liệt kê trên giao diện; các curve spline/
ellipse được xấp xỉ. Bản vẽ có OCS khác XY được bỏ qua kèm thông báo.

### Bật DWG

Tải runtime từ [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter).
Ứng dụng tự tìm trên PATH, cấu hình ezdxf hoặc `C:\Program Files\ODA\*`.
Có thể chỉ định rõ trước khi chạy backend:

```powershell
$env:ODA_FILE_CONVERTER = 'C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe'
python server.py
```

Máy phát triển hiện dùng bản portable tại `.tools/oda/runtime/ODAFileConverter.exe`,
được tự phát hiện trên Windows. Runtime không đưa vào Git. Nếu chuyển repo sang
máy khác, cần cài ODA lại. Trên Linux đặt `ODA_FILE_CONVERTER` tới executable
(hoặc AppImage có quyền chạy); app dùng Qt offscreen và timeout chuyển đổi 120 giây.
Render Python mặc định **chưa có ODA**. `Dockerfile` và `render.yaml` dùng Docker
để cài ODA Linux cùng thư viện hệ thống và màn hình ảo Xvfb (ODA bản này chỉ có
Qt xcb). Chỉ `pip install` không bật được DWG.
Docker build chạy `scripts/check_dwg_runtime.py` và dừng nếu chuyển DWG thật thất bại.

`GET /api/formats` cho biết định dạng và bộ chuyển đổi đã được tìm thấy hay chưa.
Khả năng chạy thực tế phụ thuộc runtime; nếu chuyển đổi lỗi, giao diện hiển thị lỗi.
Web và `python cli.py analyze drawing.dwg` sử dụng cùng bộ nhập.
Kiểm thử ODA thật tạo DWG từ một bản DXF rồi nhập lại để đối chiếu kích thước;
test này tự bỏ qua ở môi trường không cài ODA.

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

Dự án đã cấu hình `render.yaml` và `Dockerfile` cho DWG trên Linux:

1. Đăng nhập vào [Render.com](https://dashboard.render.com/) bằng tài khoản GitHub.
2. Bấm nút **New +** ở góc trên bên phải -> Chọn **Web Service**.
3. Chọn repository **`lax-cnc-symmetry-engine`** từ danh sách GitHub của bạn.
4. Chọn cấu hình:
   - **Language / Runtime**: `Docker`
   - **Dockerfile Path**: `./Dockerfile`
   - **Docker Command**: để trống (dùng CMD trong Dockerfile)
   - **Health Check Path**: `/api/formats`
   - **Plan**: `Free`
5. Bấm **Deploy Web Service**. Lần build đầu tải Python, thư viện và ODA nên có thể mất vài phút.

Service Python đã tạo trước đây không tự chuyển sang Docker chỉ nhờ push Git.
Cần tạo service Docker từ repo (hoặc cập nhật cấu hình runtime qua công cụ quản lý
Render nếu tài khoản hỗ trợ). Service Python vẫn đọc DXF/SVG/HPGL/G-code sau deploy,
nhưng DWG cần service Docker. File ODA của Windows trong `.tools` không được push.

Kiểm tra Docker tại local:

```bash
docker build -t cnc-symmetry .
docker run --rm -p 10000:10000 cnc-symmetry
```

Sau deploy, kiểm tra `/api/formats` có `.dwg` với `available: true` và nhập một
DWG thật. Push thành công không đồng nghĩa Render đã build/deploy thành công.

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
