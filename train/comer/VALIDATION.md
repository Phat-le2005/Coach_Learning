# Kiểm tra kỹ thuật — 2026-11-06

Đây là kết quả QA local của kit, **không phải kết quả fine-tune trên học sinh**. Chưa chạy GPU Kaggle hoặc W&B online.

| Hạng mục | Kết quả | Phạm vi |
|---|---|---|
| Manifest và collector storage | 11/11 tests pass | Token lạ, hash ảnh, padding mask, phiên bản preprocess, path escape, nhãn duyệt, smoke guard, writer/image leakage |
| Notebook | 18 cells; các code cell parse được | Chưa thực thi trong Kaggle runtime |
| Checkpoint gốc | Tải và kiểm tra Git blob thành công | Source/checkpoint tại commit lock |
| Train thật qua PyTorch | Forward/backward, optimizer step, freeze/unfreeze encoder pass | Ảnh X tổng hợp, chỉ kiểm tra cơ chế |
| Resume | Epoch 1 → resume epoch 2 có mọi tensor model giống hệt chạy 2 epoch liên tục | CPU, seed/config/dataset cố định; không suy rộng sang GPU khác |
| Checkpoint tự tạo | Load bằng safe tensor unpickler, evaluation và export thành công | Dữ liệu smoke |
| W&B SDK 0.22.3 offline | Metrics, bảng, ảnh PNG và checkpoint artifact staging được tạo | Chưa upload/tạo dashboard trên tài khoản thật |
| Collector qua browser | Vẽ → nhập nhãn → duyệt → lưu PNG/nét/manifest pass | Chromium headless, mẫu QA tổng hợp |
| ONNX FP32 checkpoint gốc | Numeric parity pass ở 3 shape/prefix khác nhau | Encoder max abs 4.77e-6; logits max abs 6.68e-6 trên tensor tổng hợp |
| ONNX FP32 checkpoint smoke | Numeric parity pass | Không thay checkpoint gốc bằng “model đã học học sinh” |
| Browser FP32 + INT8 | Cả hai chạy được engine ORT WASM, beam=3, hai độ rộng 128/320 | Hình học tổng hợp; có khác token X/x giữa FP32/INT8, cần đánh giá thật |
| Asset contract của app | ONNX I/O + vocab 113 pass | Kiểm tra tĩnh; không ghi đè model phục vụ app |

Runtime local: Windows, Python 3.13, torch 2.9.0+cpu, torchvision 0.24.0+cpu, numpy 2.2.6, ONNX 1.19.1, ONNX Runtime 1.23.2. Kiểm tra browser dùng Chrome qua Playwright.

## Lặp lại

Từ `train/comer/`, sau khi chuẩn bị môi trường:

```bash
python -m unittest discover -s tests -v
python -m comer_lab.fetch_upstream
python -m comer_lab.smoke --output data/qa-smoke
python -m comer_lab.train --config data/qa-smoke/config.json --smoke
```

Để kiểm tra resume, tạo hai cấu hình có cùng tham số train: một chạy 2 epoch liên tục; một chạy epoch 1 rồi đổi tổng epochs thành 2 và dùng `--resume latest.pt`. So sánh tất cả tensor trong `state_dict`, không so sánh byte cả file checkpoint vì metadata run khác nhau.

Browser smoke dành cho checkout đầy đủ của repo, cần frontend Node dependencies và browser Playwright:

```bash
node train/comer/tests/browser_smoke.mjs /path/to/onnx-candidate /path/to/report.json
```

Chạy lệnh trên từ gốc repo. Có thể đặt `COMER_BROWSER_CHANNEL=chrome` để dùng Chrome đã cài. Candidate chứa `encoder.onnx/decoder.onnx` hoặc `encoder_int8.onnx/decoder_int8.onnx` cùng `vocab.json`.

## Các bước còn lại trước khi công bố chất lượng

1. Tạo dataset có nhãn được duyệt, đủ người viết và split cố định.
2. Chạy baseline và fine-tune trên Kaggle, xác nhận logs/media lên W&B.
3. Chốt thí nghiệm theo validation; báo test theo số mẫu/người viết và nhóm lỗi.
4. Đo lại FP32/INT8 bằng cùng dữ liệu, decoder và cấu hình browser của app.
5. Kiểm tra thiết bị học sinh, dung lượng/latency, cache/URL phiên bản và cơ chế rollback trước khi thay model.

Không dùng các điểm số smoke làm claim pitching hoặc kết quả học thuật. Trọng số, ảnh, raw strokes, log cá nhân và cache không nằm trong commit này.
