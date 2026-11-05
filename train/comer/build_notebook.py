"""Rebuild the clean, output-free Kaggle notebook using the standard library."""
import json
from pathlib import Path
import textwrap

cells=[]
def md(text): cells.append({'cell_type':'markdown','metadata':{},'source':textwrap.dedent(text).strip().splitlines(True)})
def code(text): cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':textwrap.dedent(text).strip().splitlines(True)})

md('''
    # Coach Learning · CoMER fine-tuning
    **Kaggle GPU → W&B metrics + image tables → checkpoint → ONNX candidate.**

    Notebook dành cho nhận dạng **công thức toán viết tay**. Chưa có kết quả fine-tune trên dữ liệu học sinh.
    Đọc `train/comer/README.md` trên nhánh GitHub trước khi chạy.

    1. Bật GPU và Internet trong Kaggle. Kit dùng **một GPU**, kể cả khi phiên có nhiều GPU.
    2. Thêm private dataset gồm `manifest.jsonl` và `images/` đúng schema.
    3. Thêm Secret `WANDB_API_KEY` và cho notebook quyền dùng Secret đó.
    4. Đặt project W&B của bạn ở chế độ private nếu ảnh viết tay cần giới hạn người xem.
    5. Sửa đường dẫn và W&B entity ở cell cấu hình; chạy từ trên xuống.
''')
code('''
    from pathlib import Path
    import os, sys, subprocess, json
    REPO = "https://github.com/Phat-le2005/Coach_Learning.git"
    BRANCH = "codex/comer-kaggle-wandb"
    ROOT = Path("/kaggle/working/Coach_Learning")
    if not ROOT.exists():
        subprocess.run(["git", "clone", "--depth", "1", "--branch", BRANCH, REPO, str(ROOT)], check=True)
    LAB = ROOT / "train/comer"
    assert (LAB / "comer_lab/train.py").is_file(), "Clone thiếu train/comer; kiểm tra nhánh GitHub."
    print("Code revision:", subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())
    os.chdir(LAB)
    if str(LAB) not in sys.path: sys.path.insert(0, str(LAB))
''')
md('''
    ## Runtime
    Giữ cặp `torch`/`torchvision` CUDA do Kaggle cung cấp. Cell này không cài wheel PyTorch CPU.
    Cài thư viện trước khi import model. Nếu sửa dependencies giữa phiên, khởi động lại phiên rồi chạy lại.
''')
code('''
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(LAB / "requirements.txt")], check=True)
    import torch
    print("PyTorch:", torch.__version__, "CUDA:", torch.version.cuda)
    assert torch.cuda.is_available(), "Chưa có CUDA. Bật GPU của Kaggle rồi khởi động lại phiên."
    for i in range(torch.cuda.device_count()):
        p = torch.cuda.get_device_properties(i)
        print(i, p.name, round(p.total_memory / 1024**3, 1), "GiB")
    print("Training dùng cuda:0, không tự bật DDP.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], check=True)
''')
md('''
    ## Checkpoint gốc có kiểm tra hash
    Tải source và checkpoint CoMER tại commit cố định trong `upstream.lock.json`.
    Không dùng hai file ONNX INT8 của app làm trọng số đầu vào huấn luyện.
''')
code('''
    from comer_lab.fetch_upstream import fetch
    from comer_lab.model import UPSTREAM
    fetched = fetch(UPSTREAM)
    print("Verified upstream commit:", fetched["commit"])
''')
md('''
    ## Cấu hình thí nghiệm
    Các learning rate / batch size dưới đây là **điểm bắt đầu đề xuất**, chưa phải tham số tối ưu.
    Mỗi writer chỉ thuộc một split. Giữ test cố định và không dùng test để chọn epoch.
    `media_permission=GRANTED` mới cho phép ghi ảnh lên W&B; nhãn/dự đoán trong bảng vẫn được log.
''')
code('''
    DATA_MANIFEST = Path("/kaggle/input/coach-learning-ink/manifest.jsonl")  # SỬA đường dẫn này
    OUTPUT = Path("/kaggle/working/comer-run-01")  # thư mục mới cho run mới
    WB_ENTITY = None  # SỬA thành username/team nếu cần
    WB_PROJECT = "coach-learning-comer"
    WB_MODE = "online"  # "offline" nếu chỉ lưu log để sync sau
    RESUME_CHECKPOINT = None  # ví dụ: "/kaggle/input/comer-checkpoints/latest.pt"
    # Khi resume từ dataset, giữ best.pt cạnh latest.pt. Dùng cùng config train, chỉ tăng epochs.

    if not DATA_MANIFEST.is_file():
        print("Các manifest đang gắn vào notebook:", list(Path("/kaggle/input").rglob("manifest.jsonl")))
        raise FileNotFoundError("Gắn dataset và sửa DATA_MANIFEST; notebook không tự tạo dữ liệu huấn luyện giả.")
    config = json.loads((LAB / "config.example.json").read_text())
    config.update(manifest=str(DATA_MANIFEST), output=str(OUTPUT), upstream=str(UPSTREAM))
    config["wandb"].update(entity=WB_ENTITY, project=WB_PROJECT, mode=WB_MODE)
    # Giảm batch_size nếu OOM; không giảm độ phân giải ảnh đầu vào tùy tiện.
    CONFIG_PATH = Path("/kaggle/working/comer-config.json")
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
''')
md('''
    ## Đăng nhập W&B qua Kaggle Secrets
    Key chỉ ở bộ nhớ tiến trình; không ghi vào notebook, config hay GitHub.
''')
code('''
    if WB_MODE == "online":
        from kaggle_secrets import UserSecretsClient
        import wandb
        _wandb_key = UserSecretsClient().get_secret("WANDB_API_KEY")
        # Environment is inherited by the child training process; never print this value.
        os.environ["WANDB_API_KEY"] = _wandb_key
        del _wandb_key
    else:
        print("Offline mode: log và media lưu trong OUTPUT/wandb; chưa đồng bộ lên cloud.")
''')
md('''
    ## Train + validation
    Log: train loss/gradient norm/AMP, validation loss, ExpRate, CER, token error rate,
    tỷ lệ rỗng/truncated, thời gian; bảng ảnh–nhãn–dự đoán cố định qua các epoch.
    Artifacts có dataset fingerprint, best/latest checkpoint và thông tin runtime.

    Baseline trước fine-tune dùng **cùng validation và cùng greedy decoder**. Loss huấn luyện hai chiều.
    Checkpoint chọn theo ExpRate validation rồi loss; checkpoint lưu cuối mỗi epoch.
''')
code('''
    command = [sys.executable, "-m", "comer_lab.train", "--config", str(CONFIG_PATH)]
    if RESUME_CHECKPOINT:
        command += ["--resume", str(RESUME_CHECKPOINT)]
    try:
        subprocess.run(command, cwd=LAB, check=True)
    finally:
        os.environ.pop("WANDB_API_KEY", None)
    run_info = json.loads((OUTPUT / "run.json").read_text())
    print("W&B:", run_info.get("url") or "offline; xem OUTPUT/wandb")
''')
md('''
    ## Test sau khi chốt thí nghiệm — tùy chọn
    Bật **một lần sau khi chốt cấu hình/model**. Không dùng kết quả này chọn epoch hay chỉnh learning rate.
    Metric là greedy L2R; khi tích hợp vẫn cần benchmark browser beam=3 + bước repair của app.
''')
code('''
    RUN_FINAL_TEST = False
    if RUN_FINAL_TEST:
        subprocess.run([sys.executable, "-m", "comer_lab.evaluate",
            "--manifest", str(DATA_MANIFEST), "--checkpoint", str(OUTPUT / "best.pt"),
            "--upstream", str(UPSTREAM), "--output", str(OUTPUT / "final-test.json"),
            "--device", "cuda"], cwd=LAB, check=True)
''')
md('''
    ## Xuất ONNX candidate — tùy chọn
    Parity FP32 kiểm tra tensor số học, không chứng minh chất lượng nhận dạng.
    INT8 cần đánh giá riêng trên dữ liệu thật và browser. Không ghi đè model đang chạy trong app.
''')
code('''
    EXPORT_ONNX = False
    if EXPORT_ONNX:
        subprocess.run([sys.executable, "-m", "comer_lab.export", "--checkpoint", str(OUTPUT / "best.pt"),
            "--upstream", str(UPSTREAM), "--output", str(OUTPUT / "onnx-fp32")], cwd=LAB, check=True)
        subprocess.run([sys.executable, "-m", "comer_lab.quantize", "--source", str(OUTPUT / "onnx-fp32"),
            "--output", str(OUTPUT / "onnx-int8")], cwd=LAB, check=True)
''')
md('''
    ## Lưu kết quả
    Save Version với outputs trên Kaggle để giữ checkpoint khi phiên kết thúc.
    W&B `:best` chứa checkpoint được chọn; `:latest` sau run hoàn tất chứa **latest.pt + best.pt** để resume.
    Khi mất phiên giữa epoch, quay lại checkpoint của epoch hoàn tất gần nhất.
    Nếu dùng offline, tải outputs và chạy `wandb sync <offline-run-directory>` từ máy đã đăng nhập.
''')
code('''
    if OUTPUT.exists():
        print("Kết quả:")
        for p in sorted(OUTPUT.iterdir()):
            print(p.name, f"{p.stat().st_size / 1024**2:.1f} MiB" if p.is_file() else "directory")
        print("Không đóng phiên trước khi lưu notebook outputs / checkpoint cần giữ.")
''')

notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
    'language_info':{'name':'python','version':'3.11'}},'nbformat':4,'nbformat_minor':5}
for i,cell in enumerate(cells):cell['id']=f'coach-comer-{i:02}'
path=Path(__file__).with_name('Coach_Learning_CoMER_Kaggle.ipynb')
path.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
print(path)
