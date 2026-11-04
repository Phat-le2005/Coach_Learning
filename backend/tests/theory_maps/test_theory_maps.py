from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teacher_materials.storage import LocalTeacherMaterialStorage
from app.teachers.models import TeacherProfile
from app.theory_maps.models import TheoryMapStatus
from app.theory_maps.router import teacher_source, student_get as student_read_route, student_source
from app.theory_maps.local_draft import build_local_draft, prefill_source_steps, source_page_outline
from app.theory_maps.pdf_extraction import extract_page_texts
from app.theory_maps.schemas import TheoryLearningStep, TheoryMapRead, TheoryMapWrite, TheoryNode
from app.theory_maps.service import TheoryMapService, validate_nodes
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def pdf_bytes(page_count: int = 1, *, numbered: bool = False) -> bytes:
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    for index in range(page_count):
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        stream = DecodedStreamObject()
        text = f"{index + 1}. Derivative" if numbered else "Derivative is positive"
        stream.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def domain(db_session, tmp_path):
    users = UserService(db_session)
    teacher = users.create_user(UserCreate(email="theory-teacher@example.com", password="Secure-Test-Password-2026!", full_name="Teacher", role=Role.TEACHER))
    outsider = users.create_user(UserCreate(email="theory-other@example.com", password="Secure-Test-Password-2026!", full_name="Other", role=Role.TEACHER))
    student = users.create_user(UserCreate(email="theory-student@example.com", password="Secure-Test-Password-2026!", full_name="Student", role=Role.STUDENT))
    subject = Subject(code="THEORY-MATH", name="Math", grade_level=12)
    classroom = Classroom(name="12A", academic_year="2026-2027", grade_level=12, created_by=teacher.id)
    db_session.add_all([subject, classroom]); db_session.flush()
    teacher_profile = db_session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher.id))
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))
    db_session.add_all([
        TeacherClassroom(teacher_id=teacher_profile.id, classroom_id=classroom.id, role="OWNER"),
        StudentEnrollment(student_id=student_profile.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])
    db_session.commit()
    return teacher, outsider, student, subject, classroom, TheoryMapService(db_session, LocalTeacherMaterialStorage(tmp_path / "pdf"), 1024 * 1024)


def node(id, parent=None, *, reviewed=False, quote="Derivative is positive"):
    return TheoryNode(id=id, parent_id=parent, kind="ROOT" if parent is None else "CONCEPT",
                      title="Derivative", body="Reviewed explanation" if reviewed else "",
                      source_page=1, source_quote=quote, reviewed=reviewed)


def test_pdf_draft_review_publication_and_student_access(domain):
    teacher, outsider, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Derivative notes", "theory.pdf", pdf_bytes())
    assert row.status == TheoryMapStatus.DRAFT
    assert row.page_texts == ["Derivative is positive"]
    assert TheoryMapRead.model_validate(row).extraction_warning_pages == []
    assert service.student_list(student.id) == []
    with pytest.raises(ApplicationError): service.student_get(student.id, row.id)
    with pytest.raises(ApplicationError): service.teacher_get(outsider.id, row.id)
    with pytest.raises(ApplicationError): service.publish(teacher.id, row.id, row.revision)
    saved = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=1, nodes=[node("root"), node("child", "root")]))
    with pytest.raises(ApplicationError) as unreviewed:
        service.publish(teacher.id, row.id, saved.revision)
    assert unreviewed.value.code == "MAP_NOT_REVIEWED"
    with pytest.raises(ApplicationError) as conflict:
        service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=1, nodes=[node("root")]))
    assert conflict.value.code == "REVISION_CONFLICT"
    saved = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=saved.revision,
        nodes=[node("root", reviewed=True), node("child", "root", reviewed=True)]))
    published = service.publish(teacher.id, row.id, saved.revision)
    assert published.status == TheoryMapStatus.PUBLISHED
    assert [item.id for item in service.student_list(student.id)] == [row.id]
    assert service.student_get(student.id, row.id).nodes[1]["source_page"] == 1
    service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=published.revision, nodes=[node("root", reviewed=True)]))
    assert service.student_list(student.id) == []


def test_source_hierarchy_and_formula_validation():
    page = ["Derivative is positive"]
    with pytest.raises(ApplicationError): validate_nodes([node("root"), node("root")], page)
    with pytest.raises(ApplicationError): validate_nodes([node("root", quote="invented")], page)
    with pytest.raises(ApplicationError): validate_nodes([node("root", quote=" ")], page)
    with pytest.raises(ApplicationError): validate_nodes([node("root"), node("child", "missing")], page)
    with pytest.raises(ApplicationError): validate_nodes([node("root", "child"), node("child", "root")], page)
    with pytest.raises(ApplicationError): validate_nodes([TheoryNode(id="root", kind="ROOT", title="X", source_page=1,
        source_quote=page[0], reviewed=True), TheoryNode(id="f", parent_id="root", kind="FORMULA", title="f",
        source_page=1, source_quote=page[0], reviewed=True)], page)


def test_upload_accepts_scanned_pdf_as_source_without_local_ocr_and_unsafe_filename(domain, monkeypatch):
    teacher, _, _, subject, classroom, service = domain
    from app.theory_maps import pdf_extraction
    def no_ocr(*_args):
        raise ApplicationError(422, "PDF_OCR_NOT_CONFIGURED", "Local OCR is not installed.")
    monkeypatch.setattr(pdf_extraction, "_docling_pages", no_ocr)
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
    data = BytesIO(); writer.write(data)
    scanned = service.upload(teacher.id, classroom.id, subject.id, "Scanned", "scan.pdf", data.getvalue())
    assert scanned.page_texts == [""]
    assert service.set_source_visibility(teacher.id, scanned.id, scanned.revision, visible=True).source_available
    with pytest.raises(ApplicationError) as blank:
        service.generate(teacher.id, scanned.id)
    assert blank.value.code == "PDF_OCR_NOT_CONFIGURED"
    with pytest.raises(ApplicationError) as unsafe:
        service.upload(teacher.id, classroom.id, subject.id, "Notes", "../notes.pdf", pdf_bytes())
    assert unsafe.value.code == "INVALID_FILENAME"

def test_duplicate_pdf_does_not_remove_original(domain):
    teacher, _, _, subject, classroom, service = domain
    first = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    with pytest.raises(ApplicationError) as duplicate:
        service.upload(teacher.id, classroom.id, subject.id, "Other", "other.pdf", pdf_bytes())
    assert duplicate.value.code == "THEORY_DUPLICATE"
    assert service.storage.read(first.storage_key) == pdf_bytes()
def test_local_draft_is_cited_unreviewed_and_needs_no_ai_provider(domain):
    teacher, _, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    draft = service.generate(teacher.id, row.id)
    assert draft.status == TheoryMapStatus.DRAFT
    assert draft.ai_model is None
    assert all(item["reviewed"] is False for item in draft.nodes)
    assert "Derivative is positive" in draft.nodes[1]["source_quote"]
    assert service.student_list(student.id) == []
    with pytest.raises(ApplicationError) as duplicate:
        service.generate(teacher.id, row.id)
    assert duplicate.value.code == "MAP_ALREADY_HAS_NODES"


def test_regeneration_replaces_only_an_unreviewed_draft(domain):
    teacher, _, _, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    generated = service.generate(teacher.id, row.id)
    before_revision = generated.revision
    before_nodes = [item.copy() for item in generated.nodes]
    regenerated = service.regenerate(teacher.id, row.id, before_revision)
    assert regenerated.revision == before_revision + 1
    assert regenerated.nodes == before_nodes
    with pytest.raises(ApplicationError) as stale:
        service.regenerate(teacher.id, row.id, before_revision)
    assert stale.value.code == "REVISION_CONFLICT"
    saved = service.save(teacher.id, row.id, TheoryMapWrite(
        expected_revision=regenerated.revision,
        nodes=[node("root", reviewed=True)],
    ))
    with pytest.raises(ApplicationError) as reviewed:
        service.regenerate(teacher.id, row.id, saved.revision)
    assert reviewed.value.code == "MAP_REVIEWED"


def test_prefill_existing_draft_keeps_teacher_content_and_revision(domain):
    teacher, _, _, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    page = ("Bài 1. Hàm số\nB. CÁC DẠNG BÀI TẬP.\nDạng 1.1. Đọc đồ thị\n"
            "Bước 01. Xác định bậc của hàm số.")
    row.page_texts = [page]
    row.nodes = [node.model_dump(mode="json") for node in build_local_draft("Notes", [page])]
    topic = next(item for item in row.nodes if item["title"].startswith("Dạng "))
    topic["learning_steps"] = []
    topic["body"] = "Ghi chú giáo viên"
    service.session.commit()
    prefilled = service.prefill(teacher.id, row.id, row.revision)
    topic = next(item for item in prefilled.nodes if item["title"].startswith("Dạng "))
    assert topic["body"] == "Ghi chú giáo viên"
    assert topic["learning_steps"][0]["instruction"] == "Xác định bậc của hàm số."
    assert prefilled.revision == 2
    assert service.prefill(teacher.id, row.id, prefilled.revision).revision == 2
    with pytest.raises(ApplicationError) as stale:
        service.prefill(teacher.id, row.id, 1)
    assert stale.value.code == "REVISION_CONFLICT"
    with pytest.raises(ApplicationError) as edited:
        service.regenerate(teacher.id, row.id, 2)
    assert edited.value.code == "MAP_EDITED"


def test_local_draft_preserves_source_pages_and_is_deterministic():
    pages = ["Bài 1. Đạo hàm\nĐịnh nghĩa.\ny' = 2x",
             "Ví dụ 1.\nTính đạo hàm theo định nghĩa"]
    first = build_local_draft("Đạo hàm", pages)
    second = build_local_draft("Đạo hàm", pages)
    assert [item.model_dump() for item in first] == [item.model_dump() for item in second]
    assert {item.source_page for item in first} == {1, 2}
    assert any(item.kind == "EXAMPLE" for item in first)
    assert all(not item.reviewed for item in first)
    assert [(item.title, item.latex) for item in first if item.kind == "FORMULA"] == [("y' = 2x", "y' = 2x")]
    validate_nodes(first, pages)


def test_local_draft_uses_numbered_source_hierarchy():
    source = ["Bài 1. Hàm số\n1. Khái niệm\n1.1. Tập xác định\nĐịnh nghĩa.\n2. Đồ thị\nVí dụ 1."]
    nodes = build_local_draft("Hàm số", source)
    by_title = {node.title: node for node in nodes}
    assert by_title["1. Khái niệm"].parent_id == by_title["Bài 1. Hàm số"].id
    assert by_title["1.1. Tập xác định"].parent_id == by_title["1. Khái niệm"].id
    assert by_title["Định nghĩa."].parent_id == by_title["1.1. Tập xác định"].id
    assert by_title["2. Đồ thị"].parent_id == by_title["Bài 1. Hàm số"].id
    assert by_title["Ví dụ 1."].parent_id == by_title["2. Đồ thị"].id


def test_draft_prefills_only_complete_cited_step_sequences():
    page = ("Bài 1. Hàm số\nB. CÁC DẠNG BÀI TẬP.\n"
            "Dạng 1.1. Đọc đồ thị\n"
            "Bước 01. Xác định bậc của hàm số.\n"
            "Bước 02. Xác định giao điểm với trục tung.\n"
            "Ví dụ 1.1.1\nBước 03. Lời giải ví dụ không phải hướng dẫn.")
    nodes = build_local_draft("Hàm số", [page])
    topic = next(item for item in nodes if item.title.startswith("Dạng "))
    assert [step.instruction for step in topic.learning_steps] == [
        "Xác định bậc của hàm số.", "Xác định giao điểm với trục tung."]
    assert all(step.source_page == 1 and step.source_quote in page for step in topic.learning_steps)
    assert all(not item.reviewed for item in nodes)
    validate_nodes(nodes, [page])


@pytest.mark.parametrize("steps", [
    "Bước 01. Xác định bậc của hàm số.\nBước 01. Xác định giao điểm với trục tung.",
    "Bước 02. Xác định giao điểm với trục tung.",
])
def test_draft_does_not_guess_from_dangling_math_or_ambiguous_order(steps):
    page = "Bài 1. Hàm số\nB. CÁC DẠNG BÀI TẬP.\nDạng 1.1. Đọc đồ thị\n" + steps
    nodes = build_local_draft("Hàm số", [page])
    assert next(item for item in nodes if item.title.startswith("Dạng ")).learning_steps == []


def test_dangling_math_prefills_visible_placeholder_but_blocks_publication():
    page = ("Bài 1. Hàm số\nB. CÁC DẠNG BÀI TẬP.\nDạng 1.1. Đọc đồ thị\n"
            "Bước 01. Tính\n\uf028 f(x)\nBước 02. Kết luận.")
    nodes = build_local_draft("Hàm số", [page])
    topic = next(item for item in nodes if item.title.startswith("Dạng "))
    assert [step.instruction for step in topic.learning_steps] == ["Tính □", "Kết luận."]
    assert topic.learning_steps[0].source_quote in page
    validate_nodes(nodes, [page])
    for item in nodes:
        item.reviewed = True
        if item.kind != "ROOT" and not item.learning_steps:
            item.body = "Nội dung đã đối chiếu"
    with pytest.raises(ApplicationError) as incomplete:
        validate_nodes(nodes, [page], require_reviewed=True)
    assert incomplete.value.code == "INCOMPLETE_FORMULA"


def test_prefill_preserves_teacher_edits_and_rejects_bad_step_citation():
    page = ("Bài 1. Hàm số\nB. CÁC DẠNG BÀI TẬP.\nDạng 1.1. Đọc đồ thị\n"
            "Bước 01. Xác định bậc của hàm số.")
    nodes = build_local_draft("Hàm số", [page])
    topic = next(item for item in nodes if item.title.startswith("Dạng "))
    topic.body = "Ghi chú của giáo viên"
    topic.learning_steps = []
    assert prefill_source_steps(nodes, [page]) is nodes
    assert topic.body == "Ghi chú của giáo viên"
    assert len(topic.learning_steps) == 1
    assert prefill_source_steps(nodes, [page]) is nodes
    assert len(topic.learning_steps) == 1
    topic.learning_steps[0].source_quote = "Không có trong PDF"
    with pytest.raises(ApplicationError) as mismatch:
        validate_nodes(nodes, [page])
    assert mismatch.value.code == "STEP_SOURCE_QUOTE_MISMATCH"


def test_draft_avoids_partial_theory_and_uses_matching_numbered_ancestor():
    pages = [
        "Bài 1. Hàm số\nA. LÝ THUYẾT CHUNG.\n"
        "2. Các bài toán thường gặp.\n2.1. Cực trị đa thức.\n"
        "2.1.1. Điều kiện ban đầu.\n"
        "2.2.1. Điều kiện hình học.\n"
        "Nhận xét: Ta có biểu thức bị cắt giữa dòng\n"
        "Lưu ý: Nội dung chưa đủ ngữ cảnh\n"
        "Ví dụ 1. Từ đồ thị...",
    ]
    nodes = build_local_draft("Hàm số", pages)
    validate_nodes(nodes, pages)
    by_title = {item.title: item for item in nodes}
    assert by_title["2.2.1. Điều kiện hình học."].parent_id == by_title["2. Các bài toán thường gặp."].id
    assert by_title["2.1.1. Điều kiện ban đầu."].parent_id == by_title["2.1. Cực trị đa thức."].id
    assert not any(item.title.startswith(("Nhận xét:", "Lưu ý:", "Ví dụ")) for item in nodes)


def test_draft_uses_contents_chapters_but_omits_broken_math_and_exercise_examples():
    pages = [
        "Mục lục\n\uf026 Chủ đề 01. ĐƠN ĐIỆU HÀM SỐ\n\uf050 Dạng 1.1. Xét tính đơn điệu .......... 4",
        "A. LÝ THUYẾT CHUNG.\nĐịnh nghĩa 01.\nGiả sử \uf028 \uf029y f x\uf03d là hàm số.\n"
        "Định lý.\n01\nNếu \uf028 \uf029f x\uf0a2\uf03e 0 thì tăng.\n"
        "B. CÁC DẠNG BÀI TẬP.\n\uf050 Dạng 1.1. Xét tính đơn điệu\n"
        "\uf046 Ví dụ 1.1.1\nBài 2. Bài tập vận dụng\nA. Đáp án",
    ]
    nodes = build_local_draft("Đạo hàm", pages)
    validate_nodes(nodes, pages)
    by_title = {item.title: item for item in nodes}
    assert by_title["Chủ đề 01. ĐƠN ĐIỆU HÀM SỐ"].source_page == 1
    assert by_title["Định nghĩa 01."].parent_id == by_title["A. LÝ THUYẾT CHUNG."].id
    assert by_title["Định lý 01"].parent_id == by_title["A. LÝ THUYẾT CHUNG."].id
    assert by_title["Định lý 01"].source_quote == "Định lý. 01"
    assert by_title["Dạng 1.1. Xét tính đơn điệu"].parent_id == by_title["B. CÁC DẠNG BÀI TẬP."].id
    assert all("\uf028" not in item.title and not item.body for item in nodes)
    assert not any(item.kind == "EXAMPLE" for item in nodes)
    assert "Bài 2. Bài tập vận dụng" not in by_title

    reviewed = [item.model_copy(update={"reviewed": True}) for item in nodes]
    with pytest.raises(ApplicationError) as incomplete:
        validate_nodes(reviewed, pages, require_reviewed=True)
    assert incomplete.value.code == "THEORY_CONTENT_REQUIRED"
    completed = [item.model_copy(update={"body": "Nội dung đã đối chiếu từ PDF"})
                 if item.title in {"Định nghĩa 01.", "Định lý 01"} else
                 item.model_copy(update={"learning_steps": [TheoryLearningStep(instruction="Đối chiếu đồ thị", source_page=2)]})
                 if item.title.startswith("Dạng ") else item for item in reviewed]
    validate_nodes(completed, pages, require_reviewed=True)


def test_published_exercise_type_requires_steps_and_final_branches_need_content():
    pages = ["Derivative is positive"]
    root = node("root", reviewed=True)
    exercise = TheoryNode(id="exercise", parent_id="root", kind="SECTION", title="Dạng 1. Đơn điệu",
        body="Giải thích", source_page=1, source_quote=pages[0], reviewed=True)
    with pytest.raises(ApplicationError) as missing_steps:
        validate_nodes([root, exercise], pages, require_reviewed=True)
    assert missing_steps.value.code == "LEARNING_STEPS_REQUIRED"
    exercise.learning_steps = [TheoryLearningStep(instruction="Xét dấu đạo hàm", source_page=1)]
    validate_nodes([root, exercise], pages, require_reviewed=True)
    exercise.learning_steps[0].latex = r"\frac{□}{2}"
    with pytest.raises(ApplicationError) as incomplete_formula:
        validate_nodes([root, exercise], pages, require_reviewed=True)
    assert incomplete_formula.value.code == "INCOMPLETE_FORMULA"
    exercise.learning_steps[0].latex = None
    exercise.learning_steps = [TheoryLearningStep(instruction="Xét dấu đạo hàm", source_page=2)]
    with pytest.raises(ApplicationError) as invalid_page:
        validate_nodes([root, exercise], pages)
    assert invalid_page.value.code == "INVALID_STEP_SOURCE_PAGE"
    exercise.learning_steps = []
    exercise.title = "Ghi chú"
    exercise.body = ""
    with pytest.raises(ApplicationError) as empty_leaf:
        validate_nodes([root, exercise], pages, require_reviewed=True)
    assert empty_leaf.value.code == "LEARNING_CONTENT_REQUIRED"


def test_teacher_steps_round_trip_without_a_database_migration(domain):
    teacher, _, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    root = node("root", reviewed=True)
    exercise = TheoryNode(id="exercise", parent_id="root", kind="SECTION", title="Dạng 1. Đơn điệu",
        body="Đọc dấu của đạo hàm.", latex="f'(x)", source_page=1,
        source_quote="Derivative is positive", reviewed=True, learning_steps=[
            TheoryLearningStep(instruction="Tính đạo hàm", latex="f'(x)", source_page=1),
            TheoryLearningStep(instruction="Xét dấu trên các khoảng", source_page=1),
        ])
    saved = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=1, nodes=[root, exercise]))
    assert TheoryMapRead.model_validate(saved).nodes[1].learning_steps == exercise.learning_steps
    published = service.publish(teacher.id, row.id, saved.revision)
    assert TheoryMapRead.model_validate(service.student_get(student.id, published.id)).nodes[1].learning_steps == exercise.learning_steps


def test_font_encoded_pages_are_flagged_for_teacher_review():
    from app.theory_maps.pdf_extraction import unreliable_text_pages
    assert unreliable_text_pages(["Plain text", "x " + "\uf028" * 8, "broken \ufffd"]) == [2, 3]


def test_optional_docling_only_fills_textless_pages(monkeypatch):
    from app.theory_maps import pdf_extraction
    monkeypatch.setattr(pdf_extraction, "_docling_pages", lambda _content, count: ["From OCR"] * count)
    writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
    data = BytesIO(); writer.write(data)
    assert extract_page_texts(data.getvalue()) == ["From OCR"]


def test_local_draft_rejects_truncation_instead_of_silently_omitting_source():
    page = "\n".join(f"Bài {index}. Kiến thức {index}" for index in range(1, 401))
    with pytest.raises(ApplicationError) as too_large:
        build_local_draft("Đề cương", [page])
    assert too_large.value.code == "LOCAL_MAP_TOO_LARGE"


def test_eighty_page_pdf_generates_and_can_be_saved(domain):
    teacher, _, _, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Long notes", "long.pdf", pdf_bytes(80, numbered=True))
    assert row.page_count == 80
    draft = service.generate(teacher.id, row.id)
    assert len(draft.nodes) == 81
    assert draft.nodes[-1]["source_page"] == 80
    saved = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=draft.revision,
        nodes=[TheoryNode.model_validate(item) for item in draft.nodes]))
    assert len(saved.nodes) == 81


def test_eighty_one_page_pdf_is_rejected_before_extraction():
    with pytest.raises(ApplicationError) as too_many:
        extract_page_texts(pdf_bytes(81))
    assert too_many.value.code == "PDF_PAGE_LIMIT"


def _theory_table_sql(connection):
    return connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'theory_documents'"
    ).scalar_one()


def test_page_limit_migration_can_restore_old_limit_when_no_long_pdf(db_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from tests.migrations import load_migration

    migration = load_migration("0052_theory_map_80_pages")
    with db_engine.begin() as connection:
        assert "page_count <= 80" in _theory_table_sql(connection)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert "page_count <= 50" in _theory_table_sql(connection)
            migration.upgrade()
        assert "page_count <= 80" in _theory_table_sql(connection)


def test_page_limit_migration_refuses_downgrade_with_long_pdf(domain, db_engine):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from tests.migrations import load_migration

    teacher, _, _, subject, classroom, service = domain
    service.upload(teacher.id, classroom.id, subject.id, "Long notes", "long.pdf", pdf_bytes(80, numbered=True))
    migration = load_migration("0052_theory_map_80_pages")
    with db_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="50-page limit"):
                migration.downgrade()
        assert "page_count <= 80" in _theory_table_sql(connection)


def test_original_pdf_integrity_is_checked_before_serving(domain):
    teacher, _, _, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    response = teacher_source(row.id, teacher, service)
    assert response.media_type == "application/pdf"
    assert response.body == pdf_bytes()
    service.storage.save(row.storage_key, b"tampered")
    with pytest.raises(ApplicationError) as mismatch:
        teacher_source(row.id, teacher, service)
    assert mismatch.value.code == "SOURCE_HASH_MISMATCH"


def test_source_library_share_is_independent_of_unreviewed_map(domain):
    teacher, outsider, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Derivative notes", "notes.pdf", pdf_bytes())
    draft = service.generate(teacher.id, row.id)
    assert service.student_list(student.id) == []
    with pytest.raises(ApplicationError):
        service.student_source(student.id, row.id)
    with pytest.raises(ApplicationError) as denied:
        service.set_source_visibility(outsider.id, row.id, draft.revision, visible=True)
    assert denied.value.code == "CLASSROOM_ACCESS_DENIED"

    draft_revision = draft.revision
    shared = service.set_source_visibility(teacher.id, row.id, draft_revision, visible=True)
    assert shared.status == TheoryMapStatus.DRAFT
    assert shared.source_available is True
    assert TheoryMapRead.model_validate(shared).source_available is True
    assert [item.id for item in service.student_list(student.id)] == [row.id]
    # A draft is accessible as a source PDF, but its unreviewed text is never sent to students.
    assert student_read_route(row.id, student, service).nodes == []
    assert student_source(row.id, student, service).body == pdf_bytes()
    intruder = UserService(service.session).create_user(UserCreate(
        email="theory-unenrolled@example.com", password="Secure-Test-Password-2026!",
        full_name="Unenrolled", role=Role.STUDENT))
    with pytest.raises(ApplicationError) as denied_student:
        student_source(row.id, intruder, service)
    assert denied_student.value.code == "CLASSROOM_ACCESS_DENIED"
    with pytest.raises(ApplicationError) as stale:
        service.set_source_visibility(teacher.id, row.id, draft_revision, visible=False)
    assert stale.value.code == "REVISION_CONFLICT"
    hidden = service.set_source_visibility(teacher.id, row.id, shared.revision, visible=False)
    assert hidden.source_available is False
    assert service.student_list(student.id) == []
    with pytest.raises(ApplicationError):
        student_source(row.id, student, service)


def test_source_library_rejects_missing_or_tampered_pdf(domain):
    teacher, _, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    service.storage.save(row.storage_key, b"tampered")
    with pytest.raises(ApplicationError) as bad_share:
        service.set_source_visibility(teacher.id, row.id, row.revision, visible=True)
    assert bad_share.value.code == "SOURCE_HASH_MISMATCH"
    assert service.student_list(student.id) == []
    service.storage.save(row.storage_key, pdf_bytes())
    shared = service.set_source_visibility(teacher.id, row.id, row.revision, visible=True)
    service.storage.save(row.storage_key, b"tampered")
    with pytest.raises(ApplicationError) as bad_read:
        student_source(row.id, student, service)
    assert bad_read.value.code == "SOURCE_HASH_MISMATCH"
    assert shared.source_available is True
    service.storage.delete(row.storage_key)
    with pytest.raises(ApplicationError) as missing:
        student_source(row.id, student, service)
    assert missing.value.code == "SOURCE_UNAVAILABLE"


def test_source_outline_links_to_original_pages_without_fake_theory():
    pages = ["Mục lục\nBài 1. Đơn điệu ........ 2\nDạng 1.1. Xét dấu .... 3",
             "Bài 1. Đơn điệu\nĐịnh lý 01.\nDạng 1.1. Xét dấu\ny' = 2x",
             "Dạng 1.2. Vẽ đồ thị\n\uf028\uf029\uf028\uf029"]
    assert source_page_outline(pages) == [
        {"title": "Bài 1. Đơn điệu", "source_page": 2, "kind": "CHAPTER"},
        {"title": "Dạng 1.1. Xét dấu", "source_page": 2, "kind": "EXERCISE_TYPE"},
        {"title": "Dạng 1.2. Vẽ đồ thị", "source_page": 3, "kind": "EXERCISE_TYPE"},
    ]


def test_source_library_remains_available_when_teacher_revises_map(domain):
    teacher, _, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Notes", "notes.pdf", pdf_bytes())
    shared = service.set_source_visibility(teacher.id, row.id, row.revision, visible=True)
    saved = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=shared.revision,
        nodes=[node("root", reviewed=True), node("child", "root", reviewed=True)]))
    published = service.publish(teacher.id, row.id, saved.revision)
    assert student_read_route(row.id, student, service).nodes
    revised = service.save(teacher.id, row.id, TheoryMapWrite(expected_revision=published.revision,
        nodes=[node("root"), node("child", "root")]))
    assert revised.status == TheoryMapStatus.DRAFT
    assert revised.source_available is True
    assert student_read_route(row.id, student, service).nodes == []
    assert student_source(row.id, student, service).body == pdf_bytes()

def test_source_notebook_keeps_access_and_exact_visuals(domain):
    from app.theory_maps.router import (
        teacher_notebook, student_notebook, student_notebook_block,
    )
    teacher, outsider, student, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Derivative notes", "theory.pdf", pdf_bytes())
    teacher_book = teacher_notebook(row.id, teacher, service)
    assert teacher_book["page_count"] == 1
    assert teacher_book["total_blocks"] == 1
    assert teacher_book["sections"][0]["blocks"][0]["page"] == 1
    with pytest.raises(ApplicationError):
        teacher_notebook(row.id, outsider, service)
    with pytest.raises(ApplicationError):
        student_notebook(row.id, student, service)
    row = service.set_source_visibility(teacher.id, row.id, row.revision, visible=True)
    assert student_notebook(row.id, student, service) == teacher_book
    image = student_notebook_block(row.id, 1, 0, student, service)
    assert image.body.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.headers["cache-control"] == "private, no-store"
    with pytest.raises(ApplicationError):
        student_notebook_block(row.id, 2, 0, student, service)
    row = service.set_source_visibility(teacher.id, row.id, row.revision, visible=False)
    with pytest.raises(ApplicationError):
        student_notebook(row.id, student, service)
    stored = service.storage.root / row.storage_key
    stored.write_bytes(b"mutated")
    with pytest.raises(ApplicationError) as mismatch:
        teacher_notebook(row.id, teacher, service)
    assert mismatch.value.code == "SOURCE_HASH_MISMATCH"
def test_notebook_splits_source_regions_without_retyping_math():
    from app.theory_maps.notebook import notebook_index, notebook_image
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 14 Tf 50 700 Td (Definition 1.) Tj ET\n"
                    b"BT /F1 12 Tf 50 650 Td (x=x+1) Tj ET\n"
                    b"BT /F1 14 Tf 50 450 Td (Example 1.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    content = output.getvalue()
    book = notebook_index(content, ["Definition 1.\nExample 1."])
    blocks = book["sections"][0]["blocks"]
    assert [(block["kind"], block["title"]) for block in blocks] == [
        ("THEORY", "Definition 1"), ("EXAMPLE", "Example 1"),
    ]
    assert "latex" not in blocks[0]
    assert notebook_image(content, 1, 0).startswith(b"\x89PNG\r\n\x1a\n")
    assert notebook_image(content, 1, 1).startswith(b"\x89PNG\r\n\x1a\n")


def test_delete_theory_document(domain):
    from app.theory_maps.models import TheoryDocument
    teacher, outsider, _, subject, classroom, service = domain
    row = service.upload(teacher.id, classroom.id, subject.id, "Delete me", "notes.pdf", pdf_bytes())
    assert service.session.get(TheoryDocument, row.id) is not None

    with pytest.raises(ApplicationError) as denied:
        service.delete(outsider.id, row.id)
    assert denied.value.code == "CLASSROOM_ACCESS_DENIED"

    service.delete(teacher.id, row.id)
    assert service.session.get(TheoryDocument, row.id) is None
    with pytest.raises(OSError):
        service.storage.read(row.storage_key)


def test_source_heading_match_rejects_wrong_first_card_and_preserves_number():
    from app.theory_maps.notebook import find_heading_block
    blocks = [
        {"page": 4, "title": "Nhận xét 01", "id": "p4-b0"},
        {"page": 4, "title": "Định lý. 01", "id": "p4-b1"},
    ]
    assert find_heading_block(blocks, 4, "Nhận xét 02") is None
    assert find_heading_block(blocks, 8, "Nhận xét 01") is None
    assert find_heading_block(blocks, 4, "Định lý 1.")["id"] == "p4-b1"


def test_notebook_regions_follow_vertical_order_without_overlapping_next_heading():
    from app.theory_maps.notebook import notebook_index
    writer = PdfWriter()
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    stream = DecodedStreamObject()
    # Text objects are intentionally stored bottom-first, as in real PDFs.
    stream.set_data(b"BT /F1 14 Tf 50 400 Td (Example 2.) Tj ET\n"
                    b"BT /F1 14 Tf 50 650 Td (Definition 1.) Tj ET\n")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO(); writer.write(output)
    book = notebook_index(output.getvalue(), ["Definition 1.\nExample 2."])
    blocks = [b for section in book["sections"] for b in section["blocks"]]
    assert [b["title"] for b in blocks] == ["Definition 1", "Example 2"]
    assert blocks[0]["bottom"] <= blocks[1]["top"]


def test_full_page_coverage_in_prompt_without_dropping_pages():
    from app.theory_maps.ai_generator import build_ai_mindmap_prompt
    pages = [f"Chương 1. Bài học trang {i}\nNội dung chi tiết trang {i}." for i in range(1, 65)]
    prompt = build_ai_mindmap_prompt("Toán 12", pages)
    for i in range(1, 65):
        assert f"--- [TRANG {i}/64] ---" in prompt


def test_analyze_page_statuses():
    from app.theory_maps.pdf_extraction import analyze_page_statuses
    pages = [
        "Trang sạch bình thường",
        "Trang có ký tự đặc biệt \ue001 \ue002 \ue003 \ue004 \ue005 \ue006 \ue007 \ue008",
        "   \n\t  ",
    ]
    statuses = analyze_page_statuses(pages)
    assert statuses[0]["status"] == "PROCESSED_NATIVE"
    assert statuses[1]["status"] == "HAS_PUA_MATH"
    assert statuses[2]["status"] == "EMPTY"


def test_local_draft_lineage_and_notebook_correlation():
    from app.theory_maps.local_draft import build_local_draft
    pages = ["Chủ đề 01 · Đơn điệu hàm số\nDạng 1.1 Tìm khoảng đơn điệu\nBước 1: Tính đạo hàm."]
    draft = build_local_draft("Đơn điệu", pages)
    assert len(draft) >= 2
    assert draft[0].origin == "SOURCE_EXTRACTION"
    assert draft[1].origin == "SOURCE_EXTRACTION"


def test_pedagogical_enricher_does_not_hallucinate_fake_data():
    from app.theory_maps.pedagogical_enricher import enrich_mindmap
    from app.theory_maps.schemas import NodeKind, TheoryNode
    node = TheoryNode(
        id="n1",
        parent_id=None,
        kind=NodeKind.CONCEPT,
        title="Dạng 99.9 Dạng không có trong sgk",
        source_page=1,
        source_quote="Dạng 99.9 Dạng không có trong sgk",
    )
    result = enrich_mindmap([node], ["Dạng 99.9 Dạng không có trong sgk"])
    assert len(result) == 1
    assert result[0].id == "n1"


def test_unified_ast_formula_tables_satisfy_validation():
    from app.theory_maps.unified_ast import build_unified_ast, export_mindmap_nodes
    from app.theory_maps.service import validate_nodes
    pages = [
        "CHƯƠNG 1. NGUYÊN HÀM\nI. ĐỊNH NGHĨA\nNguyên hàm của hàm số f(x)...",
        "∫ f(x)dx = F(x) + C\nBảng nguyên hàm hàm số cơ bản\n∫ x^n dx = ...",
        "Bảng nguyên hàm hàm hợp u(x)\n∫ u'(x)f(u) dx = ...",
    ]
    ast = build_unified_ast("Nguyên hàm", pages)
    nodes = export_mindmap_nodes(ast, pages)
    validate_nodes(nodes, pages)
    formula_nodes = [n for n in nodes if n.kind == "FORMULA"]
    for fn in formula_nodes:
        assert (fn.latex or "").strip()


def test_unified_ast_groups_multi_step_procedures_into_single_method_node():
    from app.theory_maps.unified_ast import build_unified_ast, export_mindmap_nodes
    from app.theory_maps.service import validate_nodes
    page = (
        "CHƯƠNG 1. HÀM SỐ\n"
        "II. SƠ ĐỒ KHẢO SÁT VÀ VẼ ĐỒ THỊ\n"
        "Bước 1: Tìm tập xác định của hàm số\n"
        "Bước 2: Xét sự biến thiên của hàm số\n"
        "Bước 3: Vẽ đồ thị hàm số\n"
    )
    ast = build_unified_ast("Hàm số", [page])
    nodes = export_mindmap_nodes(ast, [page])
    validate_nodes(nodes, [page])

    # Must NOT have separate nodes for Bước 1, Bước 2, Bước 3
    step_titles = [n.title for n in nodes if n.title.startswith(("Bước 1", "Bước 2", "Bước 3"))]
    assert step_titles == []

    # Must have exactly 1 METHOD node grouping the steps
    method_nodes = [n for n in nodes if n.kind == "METHOD"]
    assert len(method_nodes) == 1
    proc_node = method_nodes[0]
    assert "Quy trình" in proc_node.title
    assert len(proc_node.learning_steps) == 3
    assert proc_node.learning_steps[0].instruction == "Tìm tập xác định của hàm số"
    assert proc_node.learning_steps[1].instruction == "Xét sự biến thiên của hàm số"
    assert proc_node.learning_steps[2].instruction == "Vẽ đồ thị hàm số"
