from __future__ import annotations

import json

from app.questions.group_import_service import TrustedQuestionGroupImportService


def main() -> int:
    preview = TrustedQuestionGroupImportService().preview()
    output = preview.model_dump(
        mode="json",
        exclude={"groups"},
    )
    output["group_ids"] = [group.external_group_key for group in preview.groups]
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
