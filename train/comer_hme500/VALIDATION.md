# Kết quả kiểm tra kit · cập nhật 2026-11-07

Đã thực thi trên Windows/Python 3.13.3, torch 2.9.0+cpu, torchvision 0.24.0+cpu, W&B SDK 0.22.3. **Chưa chạy full 400 train trên GPU Kaggle, chưa tạo run W&B online.** Secret chỉ có trong tài khoản Kaggle của người dùng; kit không chứa key.

| Kiểm tra thực tế | Kết quả |
|---|---|
| Audit bản HME500 ảnh đẹp | Đọc đủ 500 JPEG; train 400 / validation 50 / test 50; không trùng byte, pixel, ID hoặc chuỗi token nhãn |
| Hỗ trợ metadata cũ | Bản 6 trường cũng qua audit 500 ảnh và fit vocabulary |
| Checkpoint gốc | Git blob checkpoint `455481570a5fd0136657dd3fa20027f3a829b47f`; SHA256 `c3433f2eb70fafa829c424c922c2305f70ee50eee305674d0e9141e5db992808` |
| Vocabulary | 113 → 117; thêm `\cot`, `\cup`, `\ln`, `\vert` chỉ từ train |
| Unit tests | 34/34 pass: data/train, Git/notebook/Bash, runtime, phiên bản/tên tự động, sampler DDP, chuẩn hóa gradient và ghép cặp so sánh |
| Train PyTorch với JPG thật | 4 ảnh train + 2 ảnh validation, 2 epoch CPU; forward/backward/optimizer pass; freeze epoch 1, unfreeze epoch 2; 4 optimizer steps |
| Resume | Chạy epoch 1 rồi resume đến epoch 2; cả **673 tensor model bằng hệt** chạy liền 2 epoch cùng seed/config |
| Reload fine-tuned checkpoint | Safe tensor unpickler + strict state_dict load pass, vocab 117 |
| W&B offline | Tạo 6 bảng ảnh–GT–prediction, 13 PNG staging (ảnh/curves), metrics và checkpoint artifacts; chưa upload cloud |
| ZIP minh chứng của QA | Kiểm SHA256 đủ 18 payload file; chứa best/last, config, history CSV/JSONL, curves, audit, dự đoán; không gồm cache W&B |
| Chặn nhầm kết quả QA | Lệnh final test từ chối checkpoint `qa_only=True`; không chạy suy luận 50 test khi QA |
| Notebook bản GitHub/Bash | Toàn bộ code parse, output/execution count rỗng; helper Git trong cell khớp source; lấy mã train từ repo Coach_Learning |
| Graphify | Đã refresh AST development graph; không thêm dependency runtime |

Fingerprint bản HME500 ảnh đẹp: `f96559cf58e4bed7f370cfd9373472aa50f298e3cb0331528ad5e6b10ac054d7`.

Đường cong QA chỉ chứng minh pipeline có chạy. Các điểm số từ 4 train/2 validation và decode limit 12 **không phải kết quả chất lượng của thí nghiệm 500 ảnh** và không dùng để báo cáo cải thiện nhận dạng. Bộ 50 test thật chưa được suy luận trong quá trình chuẩn bị kit.

## Tái kiểm tra

```bash
cd train/comer_hme500
python -m unittest discover -s tests -v
python -m hme_comer.data --data /path/to/CoachLearning_500_HME100K
python build_notebook.py
```

Kiểm tra huấn luyện nhỏ trên ảnh thật: sao chép `config.example.json` thành config riêng; đặt đường dẫn dataset/output mới, `device=cpu`, `amp=false`, `epochs=2`, `batch_size=2`, `accumulate=1`, `freeze_encoder_epochs=1`, `max_decode_tokens=12`, `media_samples=2`, `wandb.mode=offline`. Fetch upstream trước, rồi chạy:

```bash
python -m hme_comer.train --config qa-config.json --qa
```

`--qa` vẫn audit đủ 500 nhưng chỉ chạy 4 train/2 validation. Mọi checkpoint và summary được đánh dấu QA. Kiểm resume bằng một run khác đến epoch 1, tăng tổng epochs thành 2 và chạy với `--resume <output>/last.pt`; so sánh tensor `state_dict` với run liền 2 epoch. Khác byte toàn file checkpoint là bình thường vì metadata run khác.

Kaggle CUDA/AMP, W&B authentication/upload và đường dẫn mount thực tế chỉ được xác nhận sau khi chạy notebook trên tài khoản Kaggle. Online mode không được ghi là đã kiểm chứng bởi thử nghiệm offline.

## Luồng Secrets → GitHub → Bash

Bản cập nhật thay cơ chế source nhúng bằng clone/pull GitHub và `scripts/run_kaggle.sh`. Các kiểm tra mới bao gồm:

- Git token không nằm trong argv hoặc URL; askpass chỉ tham chiếu biến môi trường và được xóa sau lệnh Git. Lỗi auth không in lại stderr.
- Repo sạch dùng pull fast-forward; repo có chỉnh sửa dừng và giữ dữ liệu.
- Bash `all` gọi đúng thứ tự pip → tests → checkpoint → train → final test; giữ đường dẫn chứa dấu cách.
- Lỗi cài đặt chặn các bước tiếp theo; flags resume/QA được truyền đúng; chặn final test của QA trước setup.
- Notebook dùng đúng `Phat-le2005/Coach_Learning`, không dùng repo nhận diện cảm xúc trong đoạn mã tham khảo.

Đã chạy thêm **Bash runner thật** với 4 JPEG train + 2 JPEG validation, một epoch CPU, W&B offline: baseline, optimizer step, checkpoint, CSV/PNG/ZIP được tạo thành công. Không thay đổi ảnh input và không suy luận 50 test. Đây là QA điều phối `.sh`, không là kết quả thí nghiệm đầy đủ.

Các test Git/auth dùng runner giả và token fixture, không gửi credentials ra mạng. Kiểm tra Bash dùng Python fixture cho phần điều phối; kiểm tra train nhỏ với JPG thật vẫn được tách và đánh dấu QA, không là kết quả fine-tune đầy đủ.

## Sửa tương thích W&B / Protobuf 7

Đã tái tạo đúng ImportError `Imports` bằng W&B 0.22.3 khi Protobuf 7 đã được import. Đã kiểm tra cặp **W&B 0.26.0 + Protobuf 7.35.1** trong Python 3.13 với **grpcio-tools 1.85.1**: symbol `Imports` import được, constraint khớp, `pip check` báo không có requirement lỗi. Đây là môi trường QA riêng; không sửa môi trường QA 0.22.3 cũ.

Đã chạy lại `.sh train --qa` với ảnh JPG thật, CPU, một epoch: W&B SDK 0.26.0 tạo metrics, bảng ảnh, artifact checkpoint và ZIP offline thành công. Notebook bỏ pip/import W&B trong kernel, và setup có preflight trong tiến trình mới trước unit tests/checkpoint/train. GPU Kaggle và upload W&B online vẫn chưa được kiểm chứng ở đây.

## v2/v3: hai GPU, snapshot trước fine-tune và tên tự động

Đã chạy test cho launcher `torch.distributed.run --nproc_per_node=2`, sampler chia đủ 400 ảnh không overlap, chuẩn hóa gradient theo tổng token khi hai rank có số token khác nhau, freeze/unfreeze giữ nguyên tập parameter, RNG roundtrip, tên r001/r002 và đặt tên đồng thời, ghép cặp ID/nhãn và dấu delta trước/sau. Cả 34 unit tests pass trên Windows Python 3.13, torch 2.9.0+cpu.

Đã chạy lại train **một tiến trình CPU** qua wrapper mới trên 4 JPEG train + 2 validation, 2 epoch freeze/unfreeze. Lưu initial.pt, best.pt, last.pt và checksum. Đã đánh giá initial và best trên cùng 2 validation bằng `compare --qa`, tạo CSV/JSON/PNG và hai run W&B offline cùng group. Upload retry `--sync-only` thành công sau lỗi kết nối dịch vụ local; kết quả suy luận đã lưu được giữ nguyên, không chạy lại. Không dùng các metric QA nhỏ này làm kết quả nhận dạng của 500 ảnh.

**Chưa xác nhận chạy CUDA/NCCL trên hai GPU thật hoặc W&B online.** Máy Windows không có hai GPU để kiểm tra. Thử hai rank Gloo CPU bị chặn bởi bản PyTorch Windows (`unsupported gloo device`); môi trường Linux/WSL local gặp lỗi hệ thống trước khi chạy integration. Vì vậy không báo “DDP integration pass” hay “DDP resume parity pass”. Script `tests/qa_distributed.py` được cung cấp để kiểm tra hai rank, dữ liệu rời nhau, một training W&B run và resume tensor equality trên Linux phù hợp; script này chưa hoàn tất ở môi trường local.

Mẫu kiểm tra Linux CPU, dùng ảnh thật và cache CoMER đã xác minh, chưa chạm test:

```bash
python tests/qa_distributed.py --data /path/CoachLearning_500_HME100K \
  --upstream /path/verified/upstream --root /tmp/comer-ddp-qa-new
```

Trên Kaggle, chọn **T4 x2**, chạy một trial mới bằng `bash scripts/run_kaggle.sh new v3`. Kiểm `runtime.json` (`world_size=2`, hai tên GPU), `rank-samples-NNN.json` và GPU system metrics trong W&B để xác nhận phiên thật. Hai run so sánh `-before`/`-after` chỉ đánh giá sau khi best được chọn bằng validation.
