from app.assignments.models import StudentAssignment, StudentAssignmentStatus


def recalculate_student_assignment_score(
    assignment: StudentAssignment,
    *,
    finalize: bool,
) -> float | None:
    """Return ten-point score only when every submitted item has a score."""
    scores = [
        item.score
        for item in (*assignment.student_questions, *assignment.student_material_items)
    ]
    if any(score is None for score in scores):
        assignment.score = None
        return None
    assignment.score = round(sum(scores) / len(scores) * 10, 2) if scores else 0.0
    if finalize:
        assignment.status = StudentAssignmentStatus.GRADED
    return assignment.score
