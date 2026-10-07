# EduMS API v1 Contract Specification

Thư mục này lưu trữ hợp đồng giao tiếp chính thức (OpenAPI Contract) của EduMS Backend phiên bản **v1.0.0**.

## Thứ Bậc Thẩm Quyền (Documentation Hierarchy)

1. `contracts/openapi-v1.json` (Nguồn chân lý chuẩn hóa máy đọc - Machine-readable Source of Truth)
2. `contracts/openapi-v1.sha256` (Mã băm toàn vẹn của hợp đồng đóng băng)
3. `app/api/version.py` (Hằng số phiên bản API 1.0.0)
4. `backend/API_V1.md` (Tài liệu hướng dẫn con người, được xác minh tự động bằng kiểm thử)

`openapi-v1.json is the machine-readable source of truth.`
`API_V1.md is a human guide and is automatically checked so documented METHOD/path pairs must exist in the frozen OpenAPI contract.`

Nếu có sự khác biệt giữa tài liệu diễn giải văn bản và schema OpenAPI máy đọc: **OpenAPI luôn luôn chiến thắng (OpenAPI wins)**.

## Các tệp tin trong thư mục

- `openapi-v1.json`: Đặc tả OpenAPI 3.1 hoàn chỉnh của toàn bộ API v1, được định dạng chuẩn hóa (`indent=2`, `sort_keys=True`, `ensure_ascii=False`).
- `openapi-v1.sha256`: Mã băm SHA-256 của chuỗi JSON chuẩn hóa dạng rút gọn (compact normalized), dùng để phát hiện bất kỳ thay đổi ngoài ý muốn nào trong schema.
- `API_V1_CHANGELOG.md`: Nhật ký thay đổi phiên bản hợp đồng API v1.

## Công cụ quản lý Contract CLI

Hệ thống cung cấp hai lệnh quản lý contract không phụ thuộc vào database bên ngoài:

### 1. Xuất / Đóng băng Contract (Export CLI)
```bash
# Từ thư mục backend/
python -m app.api.export_contract
```
Lệnh này khởi tạo ứng dụng ở chế độ cấu hình offline test, trích xuất `app.openapi()`, tuần tự hóa có thứ tự xác định vào `openapi-v1.json`, và cập nhật mã SHA-256 tương ứng vào `openapi-v1.sha256`.

### 2. Kiểm tra tính toàn vẹn Contract (Check CLI)
```bash
# Từ thư mục backend/
python -m app.api.check_contract
```
Lệnh này đối chiếu schema OpenAPI sinh ra từ mã nguồn hiện tại với `openapi-v1.json` và `openapi-v1.sha256`.
- Trả về mã thoát `0` nếu contract hoàn toàn khớp.
- Trả về mã thoát `1` và in diff trực quan nếu phát hiện bất kỳ sai lệch nào.

## Tích hợp CI/CD

Quy trình tự động hóa GitHub Actions (`.github/workflows/backend-data-validation.yml`) chạy `python -m app.api.check_contract` trong mỗi lần push và pull request để ngăn chặn API regression hoặc breaking change ngoài ý muốn.
