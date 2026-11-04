from __future__ import annotations

import json
from pathlib import Path


def render(path, payload):
    """One portable HTML: source crops and metadata are embedded, no CDN."""
    template = Path(__file__).with_name('viewer.html').read_text(encoding='utf-8')
    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    Path(path).write_text(template.replace('__PAIRED_PAYLOAD__', data), encoding='utf-8')
