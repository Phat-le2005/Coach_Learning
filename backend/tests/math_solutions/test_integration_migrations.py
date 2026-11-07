"""Guard the joined migration history after integrating OCR/Math Canvas."""

from tests.migrations import migration_scripts


def test_canvas_and_theory_share_one_deployable_head():
    scripts = migration_scripts()
    assert scripts.get_heads() == ["0055_assignment_delivery_mode"]
    history = {script.revision for script in scripts.walk_revisions()}
    assert {
        "0049_math_canvas",
        "0049_math_paper_attachments",
        "0050_merge_math_canvas_paper",
        "0053_theory_source_library",
    } <= history
