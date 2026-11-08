# CoMER fine-tune · Coach Learning HME500 · Local/Kaggle + W&B

Kit chạy trực tiếp trên bộ **500 ảnh JPG viết tay thật** và `metadata.json` đã có. Luồng chạy: **Kaggle Secrets → clone/pull GitHub → Bash `.sh` → CoMER + W&B**. Giữ nguyên byte ảnh gốc; chuyển grayscale/invert/resize chỉ trong bộ nhớ để đưa vào model. Không tạo ảnh AI, không sinh dataset bổ sung.

## V4 + V5 + V6: mỗi bản 50 epoch trên Kaggle T4 ×2

Chỉ chỉnh `kaggle.suite50.json`, rồi chạy từ thư mục `train/comer_hme500`:

```powershell
& ../../.tmp/comer-kaggle-control/.venv/Scripts/python.exe -m hme_comer.cloud --config kaggle.suite50.json
```

Một lệnh chạy ba trial, tối đa hai phiên Kaggle song song (`parallel_sessions=2`), mỗi phiên hai GPU: V4 decoder LR `1e-4`; V5 `5e-5`; V6 giữ V5 và thêm scale train `0.9–1.1`. V4/V5 dùng notebook chính lần lượt, V6 dùng notebook riêng. Cả ba bắt đầu từ cùng pretrained checkpoint, seed 42, encoder LR `1e-5`, freeze 2 epoch, Otsu, batch 4/GPU × 2 GPU × accumulation 2 = 16. Split cố định 400/50/50. Đây là các trial DDP2 mới, không ghi đè hoặc tiếp tục run local cũ. `early_stopping_patience=50` bảo đảm đi đủ 50 epoch; model cuối dùng checkpoint do validation chọn, không mặc định epoch 50.

Scale chỉ thay đổi tensor train sau resize cơ bản, trước khi padding; giới hạn kích thước 256×1024. RNG riêng theo seed/epoch/id không làm thay đổi RNG model/sampler. Không áp dụng augmentation cho baseline, validation hoặc test; JPG gốc và nhãn giữ nguyên. Mức 1.0/1.0 mặc định là đường xử lý cũ. Cấu hình augmentation nằm trong chữ ký checkpoint để chặn resume sai điều kiện.

Runner tự đặt tên theo version, số epoch, scale, LR, seed, batch và UTC, giữ cùng W&B project. Log epoch được đọc qua SDK stream. Sau mỗi trial, runner kiểm ZIP và đồng bộ log đo trên Kaggle nếu cần fallback offline; chỉ hỏi key một lần cho cả suite. Cuối cùng xuất một ZIP chung chứa ba ZIP riêng, link W&B, CSV và biểu đồ so sánh. `--prepare-only` xem trước ba notebook; suite không hỗ trợ `--no-wait`. Giữ cửa sổ runner mở đến khi hoàn tất. Nếu tiến trình điều khiển bị ngắt, thêm `--resume-submissions <thư-mục-submission>` để nhận lại các ID đã lưu, không khởi động lại train; giữ nguyên source/data/training. Bộ điều phối không nộp hai version cùng một notebook khi version trước còn chạy. Chạy song song giảm thời gian chờ nhưng vẫn dùng tổng quota GPU của từng phiên.

## Kaggle T4 ×2: chạy một trial bằng một config

Chỉ chỉnh `kaggle.v5.json`, rồi chạy từ thư mục `train/comer_hme500`:

```powershell
& ../../.tmp/comer-kaggle-control/.venv/Scripts/python.exe -m hme_comer.cloud --config kaggle.v5.json
```

Môi trường điều khiển cần `pip install kaggle six wandb==0.26.0 Pillow matplotlib`; không cần PyTorch local. Khi thiếu `KAGGLE_API_TOKEN`, lệnh hỏi token bằng input ẩn, không lưu key. `WANDB_API_KEY` được đọc từ Kaggle Secrets của notebook lúc chạy; config chỉ chứa tên secret. Config mặc định cập nhật notebook riêng tư `lhngphc/comer-finetune`; thay `kernel_ref`, title, dataset và entity khi dùng tài khoản khác. Bật quyền secret trong Kaggle để log online.

Runner tự sinh notebook/metadata vào `.tmp/`, yêu cầu `NvidiaTeslaT4` (T4 ×2), pin source theo commit, cài môi trường, kiểm tra, train, so sánh initial/best, xuất báo cáo validation và tạo ZIP có checksum. Không cần tự tạo/chỉnh nhiều file. Mặc định chờ job và tải ZIP về; `--no-wait` chỉ nộp job, `--prepare-only` chỉ tạo bản gửi để kiểm tra. Không tự chuyển sang CPU khi thiếu GPU.

Nếu phiên API vẫn không đọc được Kaggle Secret, job tiếp tục với W&B offline. Sau khi tải ZIP, runner hỏi W&B key bằng input ẩn và gửi các số đo đã lưu, curve, ảnh JPG validation/test và model best gọn lên cùng project. Việc đồng bộ không train hoặc suy luận lại; run ghi rõ log được upload sau khi đo trên Kaggle. ZIP giữ nguyên dữ liệu đo và checksum. Nếu bị ngắt khi đồng bộ, chạy lại với `--sync-only <đường-dẫn-ZIP>`; không nộp một job train mới.

v5 Kaggle dùng 4 ảnh mỗi GPU × 2 GPU × accumulation 2 = batch hiệu dụng 16; decoder LR 5e-5, Otsu, tối đa 30 epoch và early stopping 6. Đây là trial DDP2 mới; batch mỗi GPU khác bản local batch 1, không phải resume chính xác từ checkpoint một GPU. Mỗi lần chạy có tên/group W&B mới trong cùng project. Chỉ upload model best gọn ở cuối, giữ full initial/best/last cùng history trong `CoachLearning_CoMER_v5_Kaggle_DDP2_Results.zip`.

## v4: chạy local một GPU, tách nền Otsu và so sánh trước/sau

v4 dành cho GPU local VRAM 4 GB: batch 1 × accumulation 16 = batch hiệu dụng 16; AMP với loss scale ban đầu 1024; tối đa 30 epoch; freeze encoder 2 epoch đầu; early stopping 6. Giữ optimizer, seed, metric và split 400/50/50. Otsu áp dụng sau grayscale/invert/resize trong tensor cho **train, validation, baseline và final test**, không ghi lại JPG. v1/v2/v3 giữ cách tiền xử lý cũ và AMP scale mặc định 65536.

Từ `train/comer_hme500`, dùng Python CUDA trong venv của repo:

```powershell
& ../../.tmp/comer-baseline-gpu/.venv/Scripts/python.exe -m hme_comer.local `
  --data "DUONG_DAN/CoachLearning_500_HME100K" `
  --upstream "DUONG_DAN/cache-CoMER-da-xac-minh" `
  --epochs 30 --entity TEN_TAI_KHOAN_WANDB
```

Môi trường này cần PyTorch/torchvision bản CUDA phù hợp driver, rồi cài `requirements.txt`. Cache CoMER có thể được tải và xác minh bằng `python -m hme_comer.fetch_upstream --destination <cache>`; không dùng model/cache khác ngầm định.

Runner hỏi key bằng input ẩn khi thiếu `WANDB_API_KEY`; key chỉ ở môi trường tiến trình, không nằm trong argv/config/source. Không cần ghi key vào file hoặc gọi `wandb.login(key=...)`. Project cố định `coachlearning-handwritten-math`; mỗi lần chạy tên mới dạng `comer-hme500-v4-otsu-local-cuda1-prepost-r001-s42-eb16-<UTC>`.

Luồng local: xác thực W&B → QA 4 train/2 validation, 2 epoch freeze/unfreeze, accumulation 1 để thử 8 lần cập nhật → train đầy đủ với accumulation 16 → chọn best bằng validation → đánh giá initial/best tuần tự trên cùng 50 test → xuất báo cáo lỗi validation. QA được gắn `qa-only` và không dùng làm điểm chất lượng. Thêm `--smoke-only` nếu chỉ cần kiểm GPU/upload. Lệnh dừng nếu QA lỗi hoặc không có optimizer step; không tự chuyển sang CPU.

Mặc định lưu dưới `.tmp/comer-local-experiments/` của checkout: session JSON, log đã che key, config, checkpoint, curves, dự đoán, ZIP. W&B có run QA và group riêng cho run train/`-before`/`-after`; không tạo project mới cho từng phiên. Nếu bị ngắt sau khi đã có `last.pt`, resume cùng config bằng `python -m hme_comer.train --config <config> --resume <output>/last.pt`; giữ lại W&B ID và điều kiện thí nghiệm. Config/checkpoint có ràng buộc preprocessing để chặn đánh giá/resume nhầm cách xử lý nền.

v4 dùng `checkpoint_upload=final_inference`: vẫn ghi ảnh, metrics và curves theo epoch lên W&B, nhưng chỉ upload model best một lần ở cuối (`best-inference.pt`, giữ nguyên FP32 tensors, vocabulary và hparams). Optimizer/RNG được bỏ khỏi bản upload để giảm dung lượng; full `best.pt`/`last.pt` cho resume vẫn nằm trong output local và ZIP. v1/v2/v3 giữ chính sách `every_epoch`. Không cần gửi lại các checkpoint trung gian để có lịch sử train đầy đủ.

## Chạy trên Kaggle

1. Upload notebook `CoachLearning_CoMER_HME500_Kaggle.ipynb` vào Kaggle. Mặc định clone `https://github.com/Phat-le2005/Coach_Learning.git`, nhánh `main`, vào `/kaggle/working/Coach_Learning`.
2. Bật GPU **T4 x2** và Internet cho v2/v3. Add Input dataset `lhngphc/data-finetune-comer` đã có thư mục `CoachLearning_500_HME100K/`.
3. Add-ons → Secrets: bật checkbox cho **`WANDB_API_KEY`**, và **`GH_TOKEN`** nếu cần xác thực GitHub. Repo công khai vẫn clone được khi thiếu `GH_TOKEN`. W&B key được đặt trong `os.environ` để Bash/Python kế thừa. Git token chỉ đi vào môi trường tiến trình Git qua askpass tạm; không nằm trong URL origin hoặc Git config.
4. Giữ `DATA_ROOT=/kaggle/input/datasets/lhngphc/data-finetune-comer`. Script tự tìm `metadata.json` trong thư mục lồng, hỗ trợ cả `/kaggle/input/<slug>/...`. Nếu gắn hai bản dataset, chỉ rõ metadata muốn dùng.
5. `WANDB_ENTITY=None` dùng tài khoản sở hữu key; đổi thành username/team nếu cần. Project mặc định **`coachlearning-handwritten-math`**. Chọn `EXPERIMENT_VERSION="v3"` để so sánh trước/sau, hoặc `v2` để chỉ fine-tune hai GPU.
6. Run All. Mỗi GPU chạy một tiến trình DDP, chỉ rank 0 ghi log/checkpoint. Khi hết phiên, **Save Version với outputs** và tải `experiment_evidence.zip`.

`/kaggle/input` chỉ đọc; kết quả mới ở `/kaggle/working/comer_experiments/<tên-run>/`. Muốn giữ checkpoint làm input cho phiên sau, lưu outputs thành Kaggle Dataset mới.

## Phiên bản hai GPU và tên tự động

| Lựa chọn | GPU | Mục đích |
|---|---|---|
| v1 | 1 | Giữ luồng fine-tune một GPU để tái kiểm tra |
| v2 | 2 | Fine-tune DDP, chọn best bằng validation, đánh giá best trên test |
| v3 | 2 | Fine-tune DDP + so sánh đúng snapshot trước fine-tune với best trên cùng test |
| v4 | 1 local | Otsu cho mọi giai đoạn, batch 1/accumulation 16, so sánh initial/best |

Sau khi clone repo và truyền WANDB_API_KEY qua môi trường, mỗi lần chạy mới dùng:

```python
%cd /kaggle/working/Coach_Learning/train/comer_hme500
!bash scripts/run_kaggle.sh new v3
```

Đổi `v3` thành `v2` cho bản chỉ fine-tune. Các lệnh này **tự tạo config mới, tên mới và thư mục mới**, rồi setup/train/evaluate. Không cần tự sửa tên run. Có thể thêm `--epochs 30 --seed 123`, `--entity <team>` hoặc `--data /path/metadata.json`.

Ví dụ tên: `comer-hme500-v3-prepost-ddp2-r002-s42-eb16-<UTC>`. Số r001/r002 tự tăng trong cùng EXPERIMENT_ROOT; UTC có microsecond bảo đảm phân biệt cả khi phiên Kaggle mới không giữ registry. Muốn tiếp tục số thứ tự qua phiên mới, giữ/lưu lại thư mục registry trong outputs. Mỗi trial là một W&B group; v3 có run train và hai run `-before` / `-after` cùng group, dùng cùng tên metric để so sánh trong W&B.

Resume giữ nguyên W&B ID/tên/group và không tạo trial mới khi dùng cell resume trong notebook. Không resume checkpoint một GPU thành hai GPU: tạo run v2/v3 mới để giữ điều kiện thí nghiệm rõ ràng.

## Thí nghiệm mặc định

CoMER Fusion pretrained chính thức, source/checkpoint pin ở `ee15cdbe02467fd29f386fd554b4bc2185110fcc`; tải công khai và xác minh từng Git blob. Không dùng ONNX INT8 của app làm trọng số train.

| Thiết lập | Giá trị khởi đầu |
|---|---|
| Dữ liệu | 400 train / 50 validation / 50 test, giữ split có sẵn |
| Optimizer | AdamW, decoder LR 1e-4, encoder LR 1e-5, weight decay 0.01 |
| Batch | v2/v3: 4 mỗi GPU × 2 GPU × accumulation 2 = 16 toàn cục; v1: 4 × 4 = 16 |
| Epoch | Tối đa 20; freeze encoder 2 epoch đầu |
| Scheduler | ReduceLROnPlateau theo val loss, factor 0.5, patience 2 |
| Chọn checkpoint | Val exact match lớn nhất, hòa thì val loss nhỏ nhất |
| Dừng sớm | 6 epoch không cải thiện tiêu chí chọn |
| Nhận dạng đánh giá | Greedy L2R, tối đa 128 token; EOS bắt buộc cho exact match |
| Seed | 42; lưu RNG, thứ tự dữ liệu theo epoch, cảnh báo khi phép toán GPU không deterministic |

Đây là điểm khởi đầu, chưa phải hyperparameter tối ưu. Nếu OOM ở hai GPU: batch 2 mỗi GPU, accumulation 4 cho **run mới**. Sau khi chỉnh helper/bootstrap hoặc cell cấu hình, chạy `python build_notebook.py`. Mã train được lấy trực tiếp từ GitHub; commit được ghi vào runtime minh chứng.

DDP dùng DistributedSampler chia 400 train thành hai phần rời nhau mỗi epoch; không nhân đôi dữ liệu. Loss chuẩn hóa theo tổng token thật trên cả hai rank sau gradient accumulation. Encoder freeze bằng no_grad trong forward, giữ tập parameter DDP cố định. Rank 0 đánh giá validation bằng model gốc, broadcast metric cho scheduler/early stopping; chỉ rank 0 ghi W&B và checkpoint. Checkpoint giữ RNG riêng từng rank. `rank-samples-NNN.json` chứng minh ảnh đã giao cho từng rank. CUDA/NCCL hai GPU cần được xác nhận trên Kaggle thực tế; bộ QA Linux CPU chỉ kiểm cơ chế distributed.

## So sánh trước và sau fine-tune

Mỗi run mới lưu **initial.pt trước optimizer step đầu tiên**, cùng SHA256 được gắn vào best.pt. Baseline là checkpoint CoMER chính thức cộng phần mở rộng từ vựng từ train giống hệt model bắt đầu fine-tune; các token mới có trọng số khởi tạo, chưa được học. Đây là baseline có cùng từ vựng, không khẳng định đó là checkpoint CROHME 113 token nguyên trạng.

v3 so sánh initial.pt và best.pt sau khi chốt epoch bằng validation. Cả hai dùng cùng 50 test, ảnh nguyên gốc, preprocessing, 117 token khi dataset tương ứng, greedy decoder và giới hạn decode. Hai worker đánh giá có thể chạy đồng thời trên GPU 0 và GPU 1. Xuất `comparison-before.json`, `comparison-after.json`, `comparison.json`, `comparison.csv`, `comparison-summary.csv`, `comparison.png`, cùng bảng ảnh–GT–dự đoán trước/sau và hai run W&B. Delta là **sau trừ trước**: exact match tăng là tốt, CER/token error giảm là tốt; không mặc định kết luận fine-tune tốt hơn.

Không dùng test để chỉnh LR/epoch. `RUN_FINAL_TEST=0` giữ test chưa đánh giá; khi chốt, chạy `bash scripts/run_kaggle.sh compare OUTPUT_DIR` cho v3. Nếu upload lỗi, `compare OUTPUT_DIR --sync-only` gửi lại kết quả đã lưu. Checkpoint cũ thiếu initial.pt không được dựng baseline giả. QA dùng `compare --qa` chỉ đánh giá 2 validation và đánh dấu rõ, không dùng 50 test.

## Các lệnh .sh trên Kaggle

Khi validation chững lại, xem lỗi của checkpoint đã chọn trước khi đổi công thức train:

```bash
bash scripts/run_kaggle.sh review /kaggle/working/comer_experiments/<ten-run>
```

Lệnh tự lấy best epoch từ summary.json và chỉ đọc `validation-NNN.json`. Tạo `validation-review-eNNN.html` (ảnh JPG gốc + nhãn + dự đoán), CSV cho các mẫu chưa đúng, JSON tổng hợp theo nhóm và ZIP chứa cả ba file kèm checksum. Ảnh được nhúng nguyên byte trong HTML để tải về xem offline; có cột review_category/review_note trong CSV để ghi nhận xét thủ công. Không chạy model, không suy luận test, không gọi W&B/tạo run, không sửa nhãn hoặc checkpoint. Nếu file review đã có, giữ nguyên ghi chú; chỉ dùng `--overwrite` khi muốn thay báo cáo cũ. Dùng `--data /path/to/metadata.json` nếu dataset đã chuyển vị trí, hoặc `--epoch 15` để xem một epoch cụ thể.

Đánh giá nguyên nhân bằng ảnh validation và nhãn gốc; phân biệt lỗi ký hiệu, cách viết LaTeX, chất lượng crop và nhãn cần kiểm tra. Đây là tài liệu rà soát, không phải công cụ tự chứng minh tương đương toán học. Chọn thí nghiệm tiếp theo bằng validation; giữ tập test cho lần báo cáo sau khi chốt.

Sau khi chạy các cell clone repo và ghi config trong notebook, có thể chạy bằng cell quen thuộc:

```python
%cd /kaggle/working/Coach_Learning/train/comer_hme500
!bash scripts/run_kaggle.sh all "$COMER_CONFIG_PATH"
```

Notebook cũng gọi chính Bash runner này bằng `subprocess.run`, giữ nguyên môi trường Secrets. `all` cài requirements, chạy unit tests, tải checkpoint, train và final test. Set `os.environ["RUN_FINAL_TEST"] = "0"` để chỉ train/validation khi đang dò cấu hình. Dùng từng bước khi cần:

```bash
bash scripts/run_kaggle.sh setup
bash scripts/run_kaggle.sh train /path/to/generated-config.json
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
