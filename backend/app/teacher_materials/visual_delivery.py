"""Attach the same approved images to every authorized question view."""
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select

from app.assignments.models import AssignmentMaterialItem, AssignmentStatus, StudentAssignment, StudentAssignmentMaterialItem, StudentAssignmentStatus
from app.assignments.schemas import StudentAssignmentRead, TeacherStudentSubmissionDetail
from app.core.exceptions import ApplicationError
from app.math_solutions.schemas import ProblemRead
from app.teacher_materials.models import TeacherMaterialItem
from app.teacher_materials.pdf_import import TeacherPdfImportService

if TYPE_CHECKING:
    from app.assignments.service import AssignmentService


class QuestionVisualDelivery:
    def __init__(self, pdf: TeacherPdfImportService):
        self.pdf = pdf
        self.session = pdf.materials.session

    @staticmethod
    def question_text(item: AssignmentMaterialItem) -> str:
        return "\n".join([item.content or "", *(option.content for option in item.options)])

    def _source(self, assigned: StudentAssignmentMaterialItem | None) -> tuple[AssignmentMaterialItem, TeacherMaterialItem]:
        snapshot = assigned.assignment_material_item if assigned else None
        source = snapshot.teacher_material_item if snapshot else None
        if (snapshot is None or source is None
                or snapshot.teacher_material_item_id != assigned.teacher_material_item_id
                or snapshot.assignment_id != assigned.student_assignment.assignment_id
                or (snapshot.teacher_material_id and snapshot.teacher_material_id != source.teacher_material_id)
                or source.material.classroom_id != assigned.student_assignment.assignment.classroom_id
                or source.material.subject_id != assigned.student_assignment.assignment.subject_id):
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy hình minh họa của câu này.")
        return snapshot, source

    def student_source(self, service: AssignmentService, actor_id: UUID, assignment_id: UUID,
                       item_id: UUID) -> tuple[AssignmentMaterialItem, TeacherMaterialItem, bool]:
        student = service._student_for_user(actor_id)
        assigned = self.session.scalar(select(StudentAssignmentMaterialItem).join(StudentAssignment).where(
            StudentAssignmentMaterialItem.id == item_id,
            StudentAssignment.id == assignment_id,
            StudentAssignment.student_id == student.id,
        ))
        if assigned is None or assigned.student_assignment.assignment.status == AssignmentStatus.DRAFT:
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy hình minh họa của câu này.")
        snapshot, source = self._source(assigned)
        revealed = assigned.student_assignment.status in {StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED}
        return snapshot, source, revealed

    def teacher_source(self, service: AssignmentService, actor_id: UUID, assignment_id: UUID,
                       student_id: UUID, item_id: UUID) -> tuple[AssignmentMaterialItem, TeacherMaterialItem]:
        service.get_for_teacher(actor_id, assignment_id)
        assigned = self.session.scalar(select(StudentAssignmentMaterialItem).join(StudentAssignment).where(
            StudentAssignmentMaterialItem.id == item_id,
            StudentAssignment.assignment_id == assignment_id,
            StudentAssignment.student_id == student_id,
        ))
        return self._source(assigned)

    def problem(self, problem: ProblemRead) -> ProblemRead:
        item_id = problem.student_assignment_material_item_id
        if item_id:
            assigned = self.session.get(StudentAssignmentMaterialItem, item_id)
            snapshot, source = self._source(assigned)
            base = f"/api/student/assignments/{assigned.student_assignment_id}/material-items/{assigned.id}/assets"
            problem.visuals = self.pdf.item_visuals(source, base, self.question_text(snapshot))
        return problem

    def student_assignment(self, assignment: StudentAssignmentRead) -> StudentAssignmentRead:
        revealed = assignment.status in {StudentAssignmentStatus.SUBMITTED, StudentAssignmentStatus.GRADED}
        for question in assignment.questions:
            if not question.student_material_item_id:
                continue
            assigned = self.session.get(StudentAssignmentMaterialItem, question.student_material_item_id)
            snapshot, source = self._source(assigned)
            base = f"/api/student/assignments/{assignment.id}/material-items/{assigned.id}/assets"
            question.visuals = self.pdf.item_visuals(source, base, self.question_text(snapshot), include_references=revealed)
        return assignment

    def teacher_submission(self, submission: TeacherStudentSubmissionDetail) -> TeacherStudentSubmissionDetail:
        for question in submission.items:
            if question.source_kind != "TEACHER_MATERIAL":
                continue
            snapshot, source = self._source(self.session.get(StudentAssignmentMaterialItem, question.id))
            base = (f"/api/teacher/assignments/{submission.assignment_id}/students/{submission.student_id}"
                    f"/material-items/{question.id}/assets")
            question.visuals = self.pdf.item_visuals(source, base, self.question_text(snapshot), include_references=True)
        return submission
