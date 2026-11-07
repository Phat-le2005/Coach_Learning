# CoMER fine-tune · Coach Learning HME500 · Kaggle + W&B

Kit chạy trực tiếp trên bộ **500 ảnh JPG viết tay thật** và `metadata.json` đã có. Luồng chạy: **Kaggle Secrets → clone/pull GitHub → Bash `.sh` → CoMER + W&B**. Giữ nguyên byte ảnh gốc; chuyển grayscale/invert/resize chỉ trong bộ nhớ để đưa vào model. Không tạo ảnh AI, không sinh dataset bổ sung.

## Chạy trên Kaggle

1. Upload notebook `CoachLearning_CoMER_HME500_Kaggle.ipynb` vào Kaggle. Mặc định clone `https://github.com/Phat-le2005/Coach_Learning.git`, nhánh `main`, vào `/kaggle/working/Coach_Learning`.
2. Bật GPU và Internet. Add Input dataset `lhngphc/data-finetune-comer` đã có thư mục `CoachLearning_500_HME100K/`.
3. Add-ons → Secrets: bật checkbox cho **`WANDB_API_KEY`**, và **`GH_TOKEN`** nếu cần xác thực GitHub. Repo công khai vẫn clone được khi thiếu `GH_TOKEN`. W&B key được đặt trong `os.environ` để Bash/Python kế thừa. Git token chỉ đi vào môi trường tiến trình Git qua askpass tạm; không nằm trong URL origin hoặc Git config.
4. Giữ `DATA_ROOT=/kaggle/input/datasets/lhngphc/data-finetune-comer`. Script tự tìm `metadata.json` trong thư mục lồng, hỗ trợ cả `/kaggle/input/<slug>/...`. Nếu gắn hai bản dataset, chỉ rõ metadata muốn dùng.
5. `WANDB_ENTITY=None` dùng tài khoản sở hữu key; đổi thành username/team nếu cần. Project mặc định **`coachlearning-handwritten-math`**. Run có tên như `comer-hme500-adamw-bs16-seed42-20261106T...Z`, group `comer-crohme-to-hme500-seed42`.
6. Run All. Chỉ dùng một GPU. Khi hết phiên, **Save Version với outputs** và tải `experiment_evidence.zip`.

`/kaggle/input` chỉ đọc; không thể lưu thêm log/checkpoint ở đường dẫn input. Mọi kết quả được lưu dưới `/kaggle/working/comer-hme500-adamw-bs16-seed42-<UTC>/`. Muốn giữ checkpoint làm input cho phiên sau, lưu outputs thành Kaggle Dataset mới.

## Thí nghiệm mặc định

CoMER Fusion pretrained chính thức, source/checkpoint pin ở `ee15cdbe02467fd29f386fd554b4bc2185110fcc`; tải công khai và xác minh từng Git blob. Không dùng ONNX INT8 của app làm trọng số train.

| Thiết lập | Giá trị khởi đầu |
|---|---|
| Dữ liệu | 400 train / 50 validation / 50 test, giữ split có sẵn |
| Optimizer | AdamW, decoder LR 1e-4, encoder LR 1e-5, weight decay 0.01 |
| Batch | 4 × accumulation 4 = 16, một GPU |
| Epoch | Tối đa 20; freeze encoder 2 epoch đầu |
| Scheduler | ReduceLROnPlateau theo val loss, factor 0.5, patience 2 |
| Chọn checkpoint | Val exact match lớn nhất, hòa thì val loss nhỏ nhất |
| Dừng sớm | 6 epoch không cải thiện tiêu chí chọn |
| Nhận dạng đánh giá | Greedy L2R, tối đa 128 token; EOS bắt buộc cho exact match |
| Seed | 42; lưu RNG, thứ tự dữ liệu theo epoch, cảnh báo khi phép toán GPU không deterministic |

Đây là điểm khởi đầu, chưa phải hyperparameter tối ưu. Nếu OOM: batch 2, accumulation 8 cho **run mới**. Sau khi chỉnh helper/bootstrap hoặc cell cấu hình, chạy `python build_notebook.py` để cập nhật notebook. Mã train được lấy trực tiếp từ GitHub; commit thực tế được ghi vào runtime minh chứng.

## Các lệnh .sh trên Kaggle

Sau khi chạy các cell clone repo và ghi config trong notebook, có thể chạy bằng cell quen thuộc:

```python
%cd /kaggle/working/Coach_Learning/train/comer_hme500
!bash scripts/run_kaggle.sh all /kaggle/working/comer_hme500_config.json
```

Notebook cũng gọi chính Bash runner này bằng `subprocess.run`, giữ nguyên môi trường Secrets. `all` cài requirements, chạy unit tests, tải checkpoint, train và final test. Set `os.environ["RUN_FINAL_TEST"] = "0"` để chỉ train/validation khi đang dò cấu hình. Dùng từng bước khi cần:

```bash
bash scripts/run_kaggle.sh setup
bash scripts/run_kaggle.sh train /kaggle/working/comer_hme500_config.json
bash scripts/run_kaggle.sh test /kaggle/working/<thu-muc-run>
```

Resume dùng `train CONFIG --resume /path/last.pt`. `test OUTPUT --sync-only` gửi lại test record đã lưu nếu upload lỗi. `.sh` dừng ngay khi một bước lỗi, không chuyển sang train/test sau lỗi cài đặt. Có thể đặt `PYTHON_BIN` để chọn Python; notebook tự đặt bằng `sys.executable`. Repo có edit local sẽ được giữ nguyên và yêu cầu chọn `REPO_PATH` mới; repo sạch dùng `pull --ff-only`. Không thiết lập Git user/email toàn máy vì clone/train không cần chúng.

## Sửa lỗi W&B / Protobuf trên Kaggle

Lỗi `cannot import name 'Imports' from wandb.proto.wandb_telemetry_pb2` xuất hiện khi W&B cũ gặp Protobuf 7, kể cả trường hợp pip đã hạ phiên bản trên đĩa nhưng kernel còn giữ module 7 trong bộ nhớ. [W&B đã bổ sung hỗ trợ Protobuf 7](https://github.com/wandb/wandb/pull/11552).

Kit hiện pin **wandb==0.26.0 + protobuf==7.35.1**, phù hợp yêu cầu Protobuf của `grpcio-tools==1.85.1`. Setup chạy `hme_comer.check_runtime` trong tiến trình mới, kiểm tra đúng symbol bị lỗi và constraints W&B/grpcio-tools trước khi tải checkpoint. Notebook chỉ đọc Secrets; W&B được import trong tiến trình train, không cần import vào kernel notebook.

Nếu đang dùng cell bootstrap cũ, thay dòng cài W&B bằng:

```python
%pip install --upgrade --no-cache-dir "wandb==0.26.0" "protobuf==7.35.1"
```

Sau khi cài, **restart kernel/session** để bỏ module Protobuf đã cache, rồi chạy lại các cell Secrets → clone/pull → config → `.sh`. Thay hoặc xóa dòng cài `wandb==0.22.3` cũ để nó không bị cài lại. Bỏ `import wandb` trong bootstrap vì phần train sẽ tự import. Khi repo đã clone, cập nhật bằng `git pull --ff-only origin main` trước lệnh `.sh`.

## Những gì được ghi lại

- W&B config: tham số, số lượng từng split/nhóm, fingerprint dataset, ký hiệu mới, chế độ QA và hợp đồng metric. Artifact runtime có phiên bản Python/package, GPU/CUDA, commit source/checkpoint và SHA256 mã chạy.
- Đường cong `train/loss`, `epoch_train/loss`, `val/loss`, `val/exp_rate`, `val/cer`, `val/token_error_rate`, tỷ lệ dự đoán rỗng/chưa EOS, LR, gradient norm, AMP skip, thời gian và bộ nhớ GPU.
- Bảng **ảnh JPG gốc – nhãn LaTeX – dự đoán – exact match – CER**, cùng các ảnh validation cố định theo epoch và các lỗi lớn nhất. Có kết quả theo sáu nhóm Cơ bản/Lũy thừa/Phân số/Căn thức/Lượng giác/Giải tích. Schema 6 trường cũ cũng được hỗ trợ; nhóm được suy ra từ nhãn nếu thiếu.
- Baseline pretrained trên cùng validation trước train. Chỉ validation được dùng chọn checkpoint; final test chạy riêng sau khi chốt. `RUN_FINAL_TEST=True` chạy đủ 50 test ở cuối kế hoạch cố định; đặt False khi đang dò cấu hình.
- W&B artifacts: manifest dataset + fingerprint, source code, checkpoint có `best`/`latest`, log thí nghiệm và final test. `best` trỏ phiên bản cải thiện gần nhất; `latest` có cả best.pt + last.pt mỗi epoch đã hoàn tất.
- Bản độc lập: `history.csv` theo epoch, `metrics.jsonl` theo optimizer step, `curves.png`, `baseline-validation.json`, `validation-NNN.json`, `final-test.json`, `summary.json`, `config.json`, `runtime.json`, `vocabulary.json`, `dataset-audit.json`, `dataset-manifest.json`, `metric-contract.json`, `checksums.json`, `best.pt`, `last.pt`, `experiment_evidence.zip`.

`WANDB_MODE=offline` vẫn tạo media/log/artifact staging. Chế độ này **chưa upload** lên tài khoản W&B; giữ cả thư mục `wandb/` và chạy `wandb sync <offline-run-directory>` khi có mạng/key. Không có API key nào được ghi trong config, notebook hoặc ZIP minh chứng. Tắt tự động chụp git/diff và console W&B; source artifact dùng danh sách file chỉ định.

## Dữ liệu và giới hạn của báo cáo

Audit phải đọc được đủ 500 JPEG, không nhãn rỗng, đúng split 400/50/50; kiểm tra trùng ID, original_id, byte ảnh, pixel và chuỗi token LaTeX. Script không tự chứng minh chữ viết đẹp, độ đúng ảnh–nhãn hay loại trừ mọi near-duplicate; phần tuyển chọn đó thuộc dataset đã chuẩn bị. Metadata không cung cấp writer ID, vì vậy **không có claim writer-disjoint**.

Từ vựng mới được fit từ **400 train**, giữ nguyên ID và trọng số ký hiệu pretrained; chỉ thêm embedding/projection cho ký hiệu mới, với seed cố định. Với bộ ảnh đẹp local đã kiểm tra, các token mới là `\vert`, `\cup`, `\cot`, `\ln`. Nếu held-out có token chưa biết, dừng và báo rõ, không bỏ ảnh hoặc đổi sang PAD. Nhãn gốc được giữ nguyên; apostrophe chỉ có alias token `\prime` khi đưa vào model.

Metric là token exact match, CER và token error; không phải đánh giá tương đương toán học hoặc bộ chấm CROHME chính thức. CER có thể lớn hơn 1 do ký tự thừa. Tập 500 ảnh đã tuyển chọn đẹp không đại diện toàn bộ người viết HME100K; số lượng mỗi nhóm nhỏ. Một seed chưa đủ khẳng định cải thiện có ý nghĩa thống kê. Checkpoint pretrained lấy từ repo CROHME của tác giả; không tự khẳng định đã kiểm chứng tuyệt đối toàn bộ dữ liệu pretraining.

## Chạy lại từ terminal

Python 3.11+; cài cặp torch/torchvision phù hợp GPU trước, rồi:

```bash
cd train/comer_hme500
bash scripts/run_kaggle.sh setup
python -m hme_comer.data --data /path/to/CoachLearning_500_HME100K
bash scripts/run_kaggle.sh train config.example.json
```

Local cần sửa `data`, `output`, `device` trong bản config riêng; cung cấp `WANDB_API_KEY` qua biến môi trường nếu online. Không cài dependencies vào môi trường production của Coach Learning.

Resume cuối epoch:

```bash
python -m hme_comer.train --config config.json --resume /path/to/last.pt
python -m hme_comer.final_test --output /path/to/run --device cuda:0
python -m hme_comer.final_test --output /path/to/run --sync-only
```

Giữ **best.pt cạnh last.pt**, cùng vocabulary/fingerprint và tham số train. Được tăng tổng epochs. Nếu lấy checkpoint từ Kaggle Input, đặt output ở Working; kit sao chép best/history cần thiết sang output mới. Run online resume cùng W&B ID. Không tiếp tục từ checkpoint QA để báo kết quả thật. Nếu final test đã lưu mà upload lỗi, `--sync-only` chỉ gửi lại kết quả sẵn có.

## Push GitHub

Chỉ thêm thư mục kit; không thêm ảnh, weights, outputs hoặc key. Từ gốc repo:

```bash
git add train/comer_hme500
git diff --cached --stat
git commit -m "feat(train): add reproducible HME500 CoMER Kaggle experiment"
git push
```

Nếu index có file từ công việc khác, kiểm tra phần staged trước commit. Kit độc lập với backend/frontend, không tự thay model của app.

Nguồn: [CoMER chính thức](https://github.com/Green-Wood/CoMER), [W&B Artifacts](https://docs.coreweave.com/products/wandb/artifacts), [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks). Xem `VALIDATION.md` để biết những gì đã chạy thực tế.
