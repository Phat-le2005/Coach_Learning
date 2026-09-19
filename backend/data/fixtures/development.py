from app.classes.models import EnrollmentStatus
from data.seed.records import ClassroomFixture, ParentLinkFixture

CLASSROOMS: tuple[ClassroomFixture, ...] = (
    ClassroomFixture(
        code="MATH12_A",
        name="Grade 12 Mathematics A",
        academic_year="2026-2027",
        grade_level=12,
        teacher_code="TEACHER_MATH_01",
        enrollments=tuple(
            (f"STUDENT_{index:02d}", EnrollmentStatus.INACTIVE if index == 6 else EnrollmentStatus.ACTIVE)
            for index in range(1, 7)
        ),
    ),
    ClassroomFixture(
        code="MATH12_B",
        name="Grade 12 Mathematics B",
        academic_year="2026-2027",
        grade_level=12,
        teacher_code="TEACHER_MATH_02",
        enrollments=tuple(
            (f"STUDENT_{index:02d}", EnrollmentStatus.COMPLETED if index == 12 else EnrollmentStatus.ACTIVE)
            for index in range(7, 13)
        ),
    ),
)

PARENT_LINKS: tuple[ParentLinkFixture, ...] = tuple(
    ParentLinkFixture(parent_code=f"PARENT_{parent:02d}", student_code=f"STUDENT_{student:02d}")
    for parent, students in enumerate(((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)), start=1)
    for student in students
)
