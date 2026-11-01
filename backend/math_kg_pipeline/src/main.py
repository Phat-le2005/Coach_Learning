import hashlib
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parent.parent
    venv_site = (
        project_root / ".venv"
        / "lib"
        / f"python{sys.version_info.major}.{sys.version_info.minor}"
        / "site-packages"
    )
    if venv_site.is_dir():
        os.environ["PYTHONPATH"] = str(venv_site) + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.execv(sys.executable, [sys.executable, "-m", "src.main", *sys.argv[1:]])

from .config import (
    PDF_PATH, OUTPUT_DIR, NEO4J_URI, NEO4J_USERNAME,
    NEO4J_PASSWORD, NEO4J_DATABASE,
)
from .recognition_pipeline import run_recognition
from .graph_store import GraphStore

def main():
    pdf_path = Path(PDF_PATH)
    document_id = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    result = run_recognition(str(pdf_path), OUTPUT_DIR)
    questions = result["questions"]

    store = GraphStore(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE)
    try:
        store.initialize()
        store.save(document_id, pdf_path.name, questions)
    finally:
        store.close()

    print(f"Trang: {len(result['pages'])}")
    print(f"Câu hỏi: {len(questions)}")
    print(f"Bước lời giải ứng viên: {sum(len(q['solution_steps']) for q in questions)}")
    print(f"Vùng toán học ứng viên: {len(result['math_regions'])}")
    print(f"Block ảnh: {len(result['image_blocks'])}")
    print("Xem data/output/recognition.json; nếu bật Gemini thì xem thêm data/output/final.json.")

if __name__ == "__main__":
    main()
