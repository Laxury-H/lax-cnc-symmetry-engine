# Nâng cấp phân tích và giao diện — 11/09/2026

## Phát hiện và thay đổi

- UI đọc `id` trong khi API trả `candidate_id`, khiến các điểm số mẫu vẫn hiện.
  Đã thay bằng thẻ phương án được dựng từ dữ liệu thực; không có điểm trước khi tính.
- Bỏ nhãn AUTO_ACCEPT 97.3 cố định. Hiển thị điểm và trạng thái của phương án áp dụng.
- Đề xuất theo kiểm tra hình học, chất lượng và mức thay đổi; không đề xuất tự động
  nếu không có phương án hợp lệ duy trì/cải thiện chất lượng gốc. API từ chối áp dụng
  phương án không hợp lệ và ID không tồn tại.
- Phản chiếu tọa độ và tìm điểm gần nhất theo lô NumPy/cKDTree; giữ mẫu điểm,
  ngưỡng sai số, hàm mục tiêu và số vòng tối ưu như trước.
- A/B dùng chung bước dựng hình bốn góc. Chấm điểm tái sử dụng phân tích đối xứng.
- Lưu bốn phương án trong session để áp dụng đúng hình đã xem trước. Khi đổi tùy chọn
  khung viền hoặc đồng bộ chỉnh sửa, tính lại; xóa liên kết xuất cũ sau chỉnh sửa.
- UI chia ba bước, xem trước khi chọn, nút xem bản gốc, trạng thái/thời gian chờ,
  lỗi ngay trên trang và hỗ trợ bàn phím. Canvas gộp redraw vào mỗi animation frame.

## Đo local

Một lần trước/sau trên cùng máy Windows, Python 3.13, mẫu `samples/No2.dxf`,
không chạy profiler trong phép đo dưới đây. Thời gian có thể dao động theo tải máy.

| Công đoạn | Trước | Sau |
|---|---:|---:|
| Nạp và phân tích | 5.918 s | 0.807 s |
| Tạo bốn phương án | 92.040 s | 7.765 s |
| Đọc lại phương án đã lưu | Chưa lưu | 0.014 s |
| Áp dụng phương án đã lưu | Tính lại bốn phương án | 0.676 s |

Chạy lại: `.venv\Scripts\python scripts/benchmark_workflow.py`.
Số đo local không phải cam kết tốc độ trên Render Free hoặc file lớn hơn.

## Phương án cho No2.dxf

| Phương án | Chất lượng | Đối xứng | Mức thay đổi ước lượng |
|---|---:|---:|---:|
| A – Chuẩn hóa họa tiết | 92.70 | 100.00 | 10.20% |
| B – Đối xứng bốn góc | 92.70 | 100.00 | 10.20% |
| C – Phản chiếu trái sang phải | 88.71 | 100.00 | 1.74% |
| D – Nắn chỉnh tối thiểu | 88.71 | 100.00 | 1.74% |

A/B cùng điểm trên mẫu này; A được chọn khi hòa điểm. C/D thay đổi ít hơn nhưng
điểm tổng thấp hơn. Với file khác, hãy dùng đề xuất tính lại, không mặc định chọn A.

Mức thay đổi là ước lượng từ khoảng cách trung điểm theo hai chiều và chênh lệch
số nét, không phải phần trăm nét thực sự được sửa. Hệ thống không thể tự biết ý đồ
thẩm mỹ của người thiết kế. Đánh giá hình học cũng không thay thế kiểm tra CAM,
dao, vật liệu và mô phỏng đường cắt.

## Kiểm chứng

- Test hồi quy dùng file mẫu trong repo, không phụ thuộc thư mục Downloads.
- So sánh batch với phép phản chiếu/tìm điểm scalar ở bốn góc trục, gồm trục xiên.
- Kiểm tra cache, đổi tùy chọn, áp dụng đúng hình đã xem trước, từ chối ID sai và
  hình không hợp lệ, vô hiệu bản xuất cũ sau sửa thủ công.
- Kiểm tra trình duyệt: nạp mẫu, điểm thực A–D, xem trước và áp dụng D (88.7).

## Giới hạn còn lại

Tác vụ vẫn đồng bộ trong một worker, session lưu trong RAM và mất khi restart.
File rất lớn hoặc nhiều người dùng đồng thời cần hàng đợi xử lý cùng kho session
bền vững. Điểm nghẽn tiếp theo cần đo theo file thực tế trước khi đổi thuật toán.
