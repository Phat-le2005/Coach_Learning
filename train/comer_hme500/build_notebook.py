"""Build the output-free Kaggle notebook: Secrets -> Git clone/pull -> Bash runner."""
import json
from pathlib import Path
import textwrap

ROOT=Path(__file__).resolve().parent
cells=[]
def md(s): cells.append(dict(cell_type='markdown',metadata={},source=textwrap.dedent(s).strip().splitlines(True)))
def code(s): cells.append(dict(cell_type='code',metadata={},source=textwrap.dedent(s).strip().splitlines(True),execution_count=None,outputs=[]))

md('''
    # Coach Learning · CoMER HME500 · 2 GPUs · versioned before/after experiments
    **Luồng chạy:** Kaggle Secrets → clone/pull Coach_Learning → `.sh` cài môi trường,
    tải checkpoint, audit 500 JPG thật, baseline, train/validation, final test và ZIP minh chứng.

    Bật GPU **T4 x2** + Internet. Add Input `lhngphc/data-finetune-comer`.
    `v2` = fine-tune DDP hai GPU; `v3` = DDP hai GPU + so sánh trước/sau trên cùng 50 test.
    Mỗi lần tạo thí nghiệm mới tự có số lần chạy + UTC và thư mục riêng; resume giữ tên cũ.
    Add-ons → Secrets: bật `WANDB_API_KEY`; bật `GH_TOKEN` nếu cần xác thực GitHub.
    Repo này công khai nên cũng clone được khi không có `GH_TOKEN`.
    Key W&B được truyền qua `os.environ` để tiến trình Bash/Python kế thừa.
''')
code('''
    from pathlib import Path
    from datetime import datetime, timezone
    import json, os, subprocess, sys

    # Repo Coach Learning. Repo nhận diện cảm xúc trong ví dụ chỉ là mẫu cách chạy.
    GITHUB_USERNAME = "Phat-le2005"
    GITHUB_REPO_NAME = "Coach_Learning"
    GITHUB_REPO_BRANCH = "main"
    REPO_URL = f"https://github.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}.git"
    REPO_PATH = Path("/kaggle/working") / GITHUB_REPO_NAME

    DATA_ROOT = "/kaggle/input/datasets/lhngphc/data-finetune-comer"
    WANDB_ENTITY = None  # username/team W&B, hoặc để mặc định theo API key
    WANDB_PROJECT = "coachlearning-handwritten-math"
    WANDB_MODE = "online"  # "offline" lưu log, chưa upload
    EXPERIMENT_VERSION = "v3"  # "v2" fine-tune; "v3" fine-tune + before/after
    EXPERIMENT_ROOT = "/kaggle/working/comer_experiments"
    SEED, EPOCHS = 42, 20
    RESUME_CHECKPOINT = None  # /kaggle/input/<checkpoints>/last.pt, giữ best.pt cạnh nó
    RUN_FINAL_TEST = True  # False nếu đang dò cấu hình

''')
md('''
    ## Đọc Secrets, giữ nguyên môi trường kernel
    `GH_TOKEN` chỉ truyền vào tiến trình Git; URL origin giữ nguyên dạng công khai.
    `WANDB_API_KEY` truyền qua môi trường cho `.sh`, không ghi vào config hay notebook output.
    W&B/Protobuf được cài và kiểm tra trong tiến trình Bash/Python riêng ở bước setup.
    Cell này không import W&B vào kernel, tránh giữ cache Protobuf cũ sau khi pip đổi phiên bản.
''')
code('''
    from kaggle_secrets import UserSecretsClient

    user_secrets = UserSecretsClient()
    try:
        _github_token = user_secrets.get_secret("GH_TOKEN")
    except Exception:
        _github_token = None
    if WANDB_MODE == "online":
        try:
            os.environ["WANDB_API_KEY"] = user_secrets.get_secret("WANDB_API_KEY")
        except Exception:
            raise RuntimeError("Bật quyền Secret WANDB_API_KEY cho notebook trong Add-ons → Secrets.") from None
        if not os.environ["WANDB_API_KEY"]:
            raise RuntimeError("WANDB_API_KEY đang rỗng.")
    print("W&B:", WANDB_MODE)
    print("GitHub auth:", "GH_TOKEN ready" if _github_token else "public clone")
''')
md('''
    ## Clone/pull repo
    Helper dưới đây dùng Git askpass tạm thời. Repo có chỉnh sửa local sẽ được giữ nguyên và báo lỗi;
    repo sạch được cập nhật bằng `pull --ff-only`. Không thay đổi Git config toàn máy.
    Source helper nằm ở `train/comer_hme500/kaggle_bootstrap.py`.
''')
code((ROOT/'kaggle_bootstrap.py').read_text(encoding='utf-8'))
code('''
    try:
        LAB, CODE_REVISION = checkout_repo(REPO_URL, GITHUB_REPO_BRANCH, REPO_PATH, token=_github_token)
    finally:
        _github_token = None
    os.chdir(LAB)
    print("Repo ready:", REPO_PATH)
    print("Training directory:", LAB)
    print("Code commit:", CODE_REVISION)
''')
md('''
    ## Cấu hình thí nghiệm
    Input tự tìm `CoachLearning_500_HME100K/metadata.json`, yêu cầu 400/50/50 và JPEG đọc được.
    Output vào Working; ảnh gốc giữ nguyên. Chọn best bằng validation, test chỉ đánh giá sau khi chốt.
    LR mặc định encoder 1e-5 / decoder 1e-4; freeze encoder 2 epoch; AdamW; early stopping 6 epoch.
    DDP: batch 4 mỗi GPU × 2 GPU × accumulate 2 = global batch 16.
    v3 lưu initial.pt trước optimizer, chọn best bằng validation, so sánh hai model sau khi chốt.
    Nếu OOM: tạo config mới với batch 2, accumulate 4 để giữ global batch 16.
''')
code('''
    if str(LAB) not in sys.path: sys.path.insert(0, str(LAB))
    from hme_comer.experiments import create
    if RESUME_CHECKPOINT:
        config = json.loads((Path(RESUME_CHECKPOINT).parent / "config.json").read_text())
        config.update(data=DATA_ROOT, epochs=EPOCHS,
                      output=str(Path(EXPERIMENT_ROOT) / config["wandb"]["name"]))
        CONFIG_PATH = Path(EXPERIMENT_ROOT) / (config["wandb"]["name"] + ".resume.config.json")
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        CONFIG_PATH, config = create(EXPERIMENT_VERSION, root=EXPERIMENT_ROOT, data=DATA_ROOT,
            seed=SEED, epochs=EPOCHS, wandb_mode=WANDB_MODE, entity=WANDB_ENTITY, project=WANDB_PROJECT)
    OUTPUT = Path(config["output"])
    os.environ["PYTHON_BIN"] = sys.executable
    os.environ["RUN_FINAL_TEST"] = "1" if RUN_FINAL_TEST else "0"
    os.environ["COMER_LAB_DIR"] = str(LAB)
    os.environ["COMER_CONFIG_PATH"] = str(CONFIG_PATH)
    print("Config:", CONFIG_PATH)
    print("Output:", OUTPUT)
    print("W&B project:", WANDB_PROJECT)
    print("Run name:", config["wandb"]["name"])
    print("Version:", config["experiment_version"], "GPUs:", config["devices"])
''')
md('''
    ## Chạy qua file .sh
    Lệnh tương đương trong cell Kaggle:
    ```bash
    !bash "$COMER_LAB_DIR/scripts/run_kaggle.sh" all "$COMER_CONFIG_PATH"
    ```
    `all` = cài dependencies (giữ torch CUDA của Kaggle) → unit tests → tải source/checkpoint CoMER có hash
    → baseline validation → fine-tune → final test khi RUN_FINAL_TEST=1 → ZIP.
    Secret W&B trong os.environ được Bash và Python kế thừa tự động.
    Nếu muốn tách bước: `setup`, `train CONFIG`, `test OUTPUT`.
    Lần chạy mới tự đặt tên, từ cell Bash: `!bash scripts/run_kaggle.sh new v3`.
''')
code('''
    command = ["bash", str(LAB / "scripts/run_kaggle.sh"), "all", str(CONFIG_PATH)]
    if RESUME_CHECKPOINT:
        command += ["--resume", str(RESUME_CHECKPOINT)]
    subprocess.run(command, cwd=LAB, check=True)
''')
md('''
    ## Minh chứng: W&B, curves, lịch sử và ZIP
    W&B có config, loss/exact match/CER/LR, ảnh–GT–prediction, lỗi theo nhóm, checkpoint artifacts.
    Greedy L2R, không phải metric CROHME chính thức. Epoch 0 là baseline pretrained.
    Local CSV/JSONL/PNG tồn tại cả khi W&B offline. Save Version với outputs trước khi kết thúc phiên.
''')
code('''
    from IPython.display import display, Image as DisplayImage, FileLink
    import pandas as pd
    run_info = json.loads((OUTPUT / "run.json").read_text())
    print("W&B:", run_info.get("url") or "offline: xem thư mục wandb trong OUTPUT")
    display(DisplayImage(filename=str(OUTPUT / "curves.png")))
    display(pd.read_csv(OUTPUT / "history.csv"))
    print(json.dumps(json.loads((OUTPUT / "summary.json").read_text()), ensure_ascii=False, indent=2))
    zip_path = OUTPUT / "experiment_evidence.zip"
    print("ZIP:", zip_path)
    display(FileLink(str(zip_path)))
    if (OUTPUT / "comparison.png").exists():
        display(DisplayImage(filename=str(OUTPUT / "comparison.png")))
        display(pd.read_csv(OUTPUT / "comparison-summary.csv"))
        display(pd.read_csv(OUTPUT / "comparison.csv"))
        if (OUTPUT / "comparison-wandb.json").exists():
            print("Before/after W&B runs:", (OUTPUT / "comparison-wandb.json").read_text())
''')
for i,c in enumerate(cells): c['id']=f'hme500-comer-shell-{i:02}'
nb=dict(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
    'language_info':{'name':'python','version':'3.11'},
    'kaggle':{'accelerator':'gpu','isInternetEnabled':True,'language':'python','sourceType':'notebook'}},nbformat=4,nbformat_minor=5)
out=ROOT/'CoachLearning_CoMER_HME500_Kaggle.ipynb'
out.write_text(json.dumps(nb,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
print(out)
