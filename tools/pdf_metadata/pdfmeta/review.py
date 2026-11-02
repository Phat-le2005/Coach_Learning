from __future__ import annotations

import json
from pathlib import Path
import shutil

from PIL import Image


def crop_sources(items: list[dict], pages: list[dict], output: Path) -> None:
    lookup = {page["page_number"]: page for page in pages}
    assets = output / "assets"
    assets.mkdir(exist_ok=True)
    for index, item in enumerate(items, 1):
        for name in ("stem", "answer", "solution"):
            for number, source in enumerate(item[name]["source_spans"], 1):
                page = lookup[source["page_number"]]
                relative = f"assets/item-{index:04}-{name}-{number:02}.png"
                target = output / relative
                # Crops are always regenerated from page images and current source spans.
                with Image.open(output / page["image_path"]) as image:
                    sx, sy = image.width / page["width"], image.height / page["height"]
                    x0, y0, x1, y1 = source["bbox"]
                    bounds = (max(0, int(x0 * sx)), max(0, int(y0 * sy)),
                              min(image.width, round(x1 * sx)), min(image.height, round(y1 * sy)))
                    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
                        raise ValueError(f"Invalid crop for {item['question_id']}: {source}")
                    image.crop(bounds).save(target)
                source["asset_path"] = relative


def build_review(items: list[dict], report: dict, output: Path) -> None:
    config_path = output / "curation.json"
    curation = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else None
    sizes = {}
    for path in (output / "pages").glob("*.json"):
        page = json.loads(path.read_text(encoding="utf-8"))
        sizes[str(page["page_number"])] = [page["width"], page["height"]]
    katex = Path(__file__).parents[3] / "frontend" / "node_modules" / "katex"
    if (katex / "dist" / "katex.min.js").exists():
        target = output / "review-assets" / "katex"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("katex.min.js", "katex.min.css"):
            if not (target / name).exists():
                shutil.copy2(katex / "dist" / name, target / name)
        if not (target / "fonts").exists():
            shutil.copytree(katex / "dist" / "fonts", target / "fonts")
        if (katex / "LICENSE").exists():
            shutil.copy2(katex / "LICENSE", target / "LICENSE")
    payload = json.dumps({"items": items, "report": report, "curation": curation,
                          "page_sizes": sizes, "step_review_available": (output / "steps.html").exists()}, ensure_ascii=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("review_editor.html").read_text(encoding="utf-8")
    (output / "review.html").write_text(template.replace("__PAYLOAD__", payload), encoding="utf-8")
