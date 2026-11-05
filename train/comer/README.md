# Coach Learning — fine-tune CoMER trên Kaggle + W&B

Phần huấn luyện nằm độc lập trong `train/comer/`, không được import vào runtime ứng dụng.

- **Nhánh:** `codex/comer-kaggle-wandb`
- **Notebook:** [Coach_Learning_CoMER_Kaggle.ipynb](https://github.com/Phat-le2005/Coach_Learning/blob/codex/comer-kaggle-wandb/train/comer/Coach_Learning_CoMER_Kaggle.ipynb)
- **Mục tiêu:** thích nghi CoMER với **công thức toán viết tay** trên Math Canvas. Không nhận dạng cả đoạn lời giải tiếng Việt.
- **Trạng thái:** đã kiểm tra kỹ thuật tại local; chưa chạy Kaggle, chưa kết nối tài khoản W&B của bạn, chưa có đánh giá fine-tune trên chữ viết học sinh.

## 1. Đưa lên Kaggle

1. Import notebook từ liên kết GitHub ở trên vào Kaggle, hoặc tải file `.ipynb` rồi import.
2. Bật **GPU + Internet**. Notebook dùng một GPU (`cuda:0`), không tự dùng cả hai GPU.
3. Gắn **private dataset** có `manifest.jsonl` và `images/` theo mục 3.
4. Trong Kaggle Secrets, thêm `WANDB_API_KEY` và bật quyền truy cập cho notebook.
5. Trong cell cấu hình, sửa `DATA_MANIFEST`, `WB_ENTITY` nếu dùng team, và `WB_PROJECT`.
6. Chạy các cell theo thứ tự. Notebook clone **đúng nhánh train** này và in commit đang dùng.

Key được lấy bằng `UserSecretsClient`, truyền trong môi trường của tiến trình train rồi xóa khỏi môi trường notebook. Không dán key vào notebook hoặc file cấu hình. Quy trình Secrets theo [tài liệu Kaggle chính thức](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md#using-secrets-in-kernels).

Notebook giữ cặp PyTorch/torchvision CUDA của Kaggle. Không cài torch CPU. Bộ thư viện phụ được cố định trong `requirements.txt`; runtime GPU cụ thể và hash source được ghi lại trong kết quả. GPU, quota và phiên bản image Kaggle có thể khác giữa các phiên.

## 2. Model và cách fine-tune

```text
Nét viết → raster đúng preprocessor app → grayscale PNG + padding mask
         → DenseNet encoder → Transformer decoder + coverage attention → LaTeX
                ↑ fine-tune checkpoint FP32 CoMER gốc
                ↓ checkpoint được chọn bằng validation
             ONNX FP32 → kiểm tra parity → INT8 candidate → benchmark browser
```

- Upstream: [Green-Wood/CoMER](https://github.com/Green-Wood/CoMER), commit `ee15cdbe02467fd29f386fd554b4bc2185110fcc`.
- `upstream.lock.json` chứa Git blob SHA và kích thước từng file; downloader và loader kiểm tra source/checkpoint gốc.
- Kiến trúc checkpoint: DenseNet, `d_model=256`, 3 decoder layers, 8 attention heads, coverage attention, **113 token**.
- Khởi đầu từ **checkpoint PyTorch gốc**, không train trực tiếp hai file ONNX INT8 đang phục vụ app.
- Train bằng cross entropy hai chiều L2R/R2L của upstream. Vòng lặp PyTorch mới không gọi Trainer Lightning đời cũ.
- Đề xuất mặc định: freeze encoder 2 epoch, LR decoder `1e-4`, encoder `1e-5`, batch 4 công thức, accumulate 4, AMP trên CUDA. Đây là cấu hình khởi đầu, chưa tối ưu.
- Dữ liệu đầu vào là ảnh đã raster hóa. Kit chưa học trực tiếp thời gian/áp lực bút; chưa bổ sung từ vựng ngoài 113 token.

## 3. Chuẩn bị dữ liệu

### Thu thập từ công cụ local

Clone nhánh này về máy, tạo môi trường Python riêng và cài requirements; cài cặp torch/torchvision phù hợp riêng nếu máy chưa có. Python 3.10+; local QA dùng Python 3.13, torch 2.9.0+cpu và torchvision 0.24.0+cpu.

```bash
cd train/comer
python -m pip install -r requirements.txt
python -m comer_lab.collect --output data/collection
```

Mở `http://127.0.0.1:8778`. Mỗi mẫu:

1. Chọn mã ẩn danh `writer_001` và split cố định của người đó.
2. Viết **một công thức**; nhập LaTeX khớp với nét viết.
3. Xem ảnh model, duyệt nhãn, xác nhận quyền dùng huấn luyện rồi lưu.
4. Bật quyền media riêng nếu cho phép ghi ảnh lên W&B.

Collector dùng **chính hàm preprocessStrokes đang được app vendored**; kiểm tra hash phiên bản trước khi chạy. Dữ liệu và nét gốc chỉ lưu ở máy local. Collector không truy vấn database app.

### Cấu trúc Kaggle Dataset

Đưa **nội dung** `data/collection/` lên một dataset riêng:

```text
coach-learning-ink/
  manifest.jsonl
  images/
    ink_....png
  strokes/                # giữ lại để audit/tái xử lý; trainer chỉ đọc PNG
    ink_....json
```

Mỗi dòng manifest là một JSON object, ví dụ minh họa schema:

```json
{
  "sample_id": "ink_unique_id",
  "writer_id": "writer_001",
  "image_path": "images/ink_unique_id.png",
  "image_sha256": "<SHA256 của file PNG thực tế>",
  "latex_verbatim": "x^{2}+1=0",
  "split": "train",
  "source": "coach_canvas_collector",
  "review_status": "APPROVED",
  "usage_permission": "GRANTED",
  "media_permission": "GRANTED",
  "preprocess_version": "ink-on-0.1.0-frozen-v1",
  "content_height": 128,
  "content_width": 216,
  "expression_family_id": "quadratic_01"
}
```

`content_height/content_width` là phần ảnh hợp lệ sau scale, **không phải bbox nét viết**; collector tính tự động. Phần còn lại của ảnh là padding đen. PNG mode `L`, cao 256 px, rộng 128–1024 px, chia hết cho 64; nét trắng trên nền đen. Không đưa ảnh chụp/trang PDF trực tiếp vào schema này.

Trainer từ chối: ảnh đổi hash, nhãn chưa duyệt, token lạ, ảnh rỗng, sai mask/version, ảnh trùng, người viết xuất hiện ở nhiều split. Dữ liệu smoke bị từ chối trừ khi có cờ `--smoke`.

**Chia theo người viết trước khi thu thập**, chẳng hạn 70/15/15 theo nhóm writer khi có đủ người. Cần nhiều kiểu nét; ưu tiên phân số, mũ/chỉ số, căn, ngoặc, dấu âm, nhầm 1/l và x/×. Báo riêng số người và mẫu của từng split. Nếu muốn đo tổng quát hóa sang cấu trúc công thức mới, cần thêm tập **expression-family-disjoint**; kiểm tra hiện tại mới báo số nhóm công thức giao nhau.

Kit không kèm dữ liệu học sinh hoặc dataset công khai đã được duyệt. Nếu nhập CROHME/dataset khác, phải giữ nguồn, quyền dùng và nhãn chuẩn, đồng thời xử lý đúng pipeline ảnh của phiên bản này.

## 4. W&B sẽ hiển thị gì?

| Nhóm | Nội dung |
|---|---|
| Train | Loss theo optimizer step, gradient norm, LR encoder/decoder, trạng thái freeze, AMP skip |
| Validation | Loss, ExpRate, CER, token error rate, empty rate, truncation rate |
| Ảnh | Gallery `validation/ink`: ảnh + caption nhãn/dự đoán |
| Bảng | `validation/predictions`: sample ID, ảnh, nhãn, dự đoán, exact match, token edits, EOS |
| Artifacts | Tóm tắt dataset + fingerprint, checkpoint best/latest, runtime và metric contract |

Giữ project W&B private nếu cần giới hạn người xem ảnh. `media_permission=GRANTED` mới log ảnh; bảng vẫn log nhãn/dự đoán. Raw strokes và toàn bộ dataset không được tự upload thành artifact. `media_samples=16` giữ cố định cùng một nhóm validation qua các epoch, tránh tải hàng nghìn ảnh mỗi epoch.

Tạo các panel line chart cho `train/loss`, `val/loss`, `val/exp_rate`, `val/cer`; đặt gallery và bảng dự đoán cạnh nhau để xem lỗi cụ thể. SDK cũng ghi thống kê hệ thống mà môi trường hỗ trợ. API cơ bản theo [W&B SDK chính thức](https://github.com/wandb/wandb).

### Hiểu đúng metric

- **ExpRate:** đúng toàn bộ chuỗi token và có EOS, từ 0 đến 1.
- **CER:** khoảng cách chỉnh sửa ký tự trên LaTeX ghép token / tổng số ký tự nhãn.
- **Token error rate:** khoảng cách chỉnh sửa token / tổng số token nhãn.
- **Loss:** teacher forcing hai chiều, chuẩn hóa theo số token không PAD.
- Validation giải mã **greedy L2R**, chưa phải bidirectional beam của paper hay beam=3 + repair của app.

Baseline trước train và từng epoch dùng cùng validation/decoder. Chọn best theo ExpRate validation, nếu bằng nhau chọn loss thấp hơn. Test chỉ chạy bằng cell riêng sau khi chốt thí nghiệm. Không dùng kết quả test để chỉnh tham số.

## 5. Checkpoint và chạy tiếp

`latest.pt` giữ model, optimizer, AMP scaler, epoch, optimizer step, RNG và fingerprint dữ liệu. Checkpoint được ghi atomic **cuối epoch**. Nếu phiên mất giữa epoch, phải chạy lại epoch đó.

- W&B artifact `comer-<run_id>:best`: checkpoint tốt nhất theo validation.
- Artifact `:latest` khi run hoàn tất: cả `latest.pt` và `best.pt` để resume.
- Trong lúc run đang chạy, checkpoint gần nhất vẫn nằm ở Kaggle `OUTPUT`; lưu outputs để giữ các epoch chưa cải thiện.
- Khi mở phiên mới, gắn thư mục checkpoint vào notebook, đặt `RESUME_CHECKPOINT` trỏ tới `latest.pt`; giữ `best.pt` cạnh nó. Sửa `OUTPUT` sang thư mục working mới, giữ các tham số train giống run cũ và tăng tổng `epochs`.
- Online resume dùng cùng W&B run ID. Dữ liệu/nhãn/split hoặc config train đổi sẽ bị từ chối; muốn đổi thì tạo thí nghiệm mới.

Offline: đặt `WB_MODE="offline"`. Cả artifact staging/cache và media nằm trong thư mục output để tải về cùng log. Trên máy đã đăng nhập W&B:

```bash
wandb sync /path/to/output/wandb/offline-run-...
```

Khi chuyển các log offline sang máy khác, giữ nguyên `wandb-data/` và `wandb-cache/`. Đường dẫn artifact trong log có thể là đường dẫn tuyệt đối của phiên cũ; cách chắc chắn nhất là sync trong cùng môi trường trước khi kết thúc phiên, hoặc phục hồi cùng đường dẫn. Không coi việc tải riêng file `.wandb` là đủ để giữ toàn bộ media.

## 6. Lệnh CLI tương đương notebook

Chạy từ `train/comer/`:

```bash
python -m comer_lab.fetch_upstream
python -m comer_lab.train --config config.json
python -m comer_lab.train --config config.json --resume runs/run-01/latest.pt
python -m comer_lab.evaluate --manifest data/collection/manifest.jsonl --checkpoint runs/run-01/best.pt --output runs/run-01/final-test.json --device cuda
python -m comer_lab.export --checkpoint runs/run-01/best.pt --output runs/run-01/onnx-fp32
python -m comer_lab.quantize --source runs/run-01/onnx-fp32 --output runs/run-01/onnx-int8
```

ONNX xuất theo đúng input/output của browser; INT8 dùng dynamic quantization QUInt8. FP32 export thay riêng MaskBatchNorm ở chế độ eval bằng biểu thức tương đương để bỏ dynamic scatter; không thay model đang train. Không ghi đè `frontend/public/ocr/comer/v0_1/`. Cần đánh giá FP32/INT8 trên cùng test, chạy browser/thiết bị thật và dùng URL phiên bản mới trước khi tích hợp.

## 7. Kiểm tra đã thực hiện

Xem [VALIDATION.md](VALIDATION.md). Kiểm tra local gồm manifest, forward/backward checkpoint gốc, W&B offline media/artifacts, resume, ONNX numeric parity và WASM browser smoke. **Các mẫu kiểm tra là hình tổng hợp; không được trích kết quả đó thành độ chính xác trên học sinh.**

```bash
python -m unittest discover -s tests -v
python -m comer_lab.smoke --output data/synthetic-smoke
python -m comer_lab.train --config data/synthetic-smoke/config.json --smoke
```

Không commit `.cache/`, `data/`, `runs/`, `wandb/`, checkpoints, ONNX hay API keys. Nhánh chỉ chứa notebook, công cụ và tài liệu; upstream được tải lúc chạy với kiểm tra hash.
