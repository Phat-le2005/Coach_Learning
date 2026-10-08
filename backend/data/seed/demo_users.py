from data.seed.records import UserSeed
from data.synthetic import generate_students
from app.users.models import Role

ADMIN = UserSeed("ADMIN_01", "admin.demo@example.com", "Demo Administrator", Role.ADMIN)
TEACHERS: tuple[UserSeed, ...] = (
    UserSeed("TEACHER_MATH_01", "teacher.math01.demo@example.com", "Demo Mathematics Teacher 01", Role.TEACHER),
    UserSeed("TEACHER_MATH_02", "teacher.math02.demo@example.com", "Demo Mathematics Teacher 02", Role.TEACHER),
)
STUDENTS = generate_students(12)
PARENTS: tuple[UserSeed, ...] = tuple(
    UserSeed(
        code=f"PARENT_{index:02d}",
        email=f"parent{index:02d}.demo@example.com",
        full_name=f"Demo Parent {index:02d}",
        role=Role.PARENT,
    )
    for index in range(1, 5)
)
USERS: tuple[UserSeed, ...] = (ADMIN, *TEACHERS, *STUDENTS, *PARENTS)
