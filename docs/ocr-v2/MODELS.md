# Local model catalogue

Models/cache nằm trong `.tmp/`, không commit và không phụ thuộc worktree cũ.
Setup: [LOCAL_SETUP](../../LOCAL_SETUP.md). Không tải BF16/base model thay checkpoint.

| Thành phần | Nguồn / version | License và identity |
|---|---|---|
| CoMER | `frontend/public/ocr/comer/v0_1`, ink-on0.1.0, ORT1.24.2 | Assets/license đã nằm trong Git; giữ nguyên encoder/decoder/vocab/runtime đồng bộ. |
| PP-DocLayout-M | PaddlePaddle/PP-DocLayout-M, revision pin trong `tools/ocr-v2-lab/download_models.py` | Apache-2.0; downloader lưu file bytes/SHA256 vào manifest; CPU/Paddle3.2.2 + PaddleOCR3.3.2. |
| VietOCR | DungHugging/vietocr-handwritten-finetune @ `0827b42e17cb0e1c1bbda5aac11f7cc5c816e0ca` | Model card khai MIT, không có standalone LICENSE trong checkpoint; lưu pinned card. `transformerocr.pth`151811471 bytes, SHA256 `d5357730c328e40dd1aeae7288994d8ad85979f8334c03c9bfad53c320114fa7`. Runtime VietOCR0.3.13/Torch2.5.1 CPU. |
| Uni-MuMER | Fine-tune phxember/Uni-MuMER-Qwen3.5-2B; GGUF mradermacher/Uni-MuMER-Qwen3.5-2B-GGUF @ `9451fe296d68348d751adc6e71e32be810e6f489` | Apache-2.0 theo pinned metadata. Q4_K_M1274397280 bytes, SHA256 `05eaa7c1593c1ba52d7b9ee848bd8303523be764e781aec9cb88a4442198f680`; mmproj-Q8_0364664704 bytes, SHA256 `a6b5c31b91655f23cfba7828eeeb992cefcc99ae75f45580187af674b6cbce28`. |
| llama.cpp | Official Windows binary release `b11960` | MIT; downloader kiểm official asset digest. CUDA packages có điều khoản NVIDIA đi kèm; CPU là mặc định setup, CUDA optional. |

Nguồn tải chính xác nằm trong downloader được version-control. Manifest được sinh
sau setup ghi revision, byte size, hash, license/source và runtime; không coi file
`.part` là download thành công. Không dùng model base/Qwen3-VL thay Uni fine-tune.

MathWriting/CROHME không phải app dependencies; không đưa corpus vào Git. License
MathWriting/CROHME có giới hạn phi thương mại; giữ attribution và kiểm điều kiện
trước khi tái phân phối hoặc dùng thương mại. Không có model/corpus nào được tải
ngầm trong request production. CoMER vẫn là mặc định; chưa có bằng chứng đủ để
đổi Uni thành recognizer mặc định hoặc auto fallback trên mọi scope.
