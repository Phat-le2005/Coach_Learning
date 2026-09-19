from data.seed.records import UserSeed
from data.synthetic import generate_students
from app.users.models import Role

ADMIN = UserSeed("ADMIN_01", "admin.demo@edums.local", "Demo Administrator", Role.ADMIN)
TEACHERS: tuple[UserSeed, ...] = (
    UserSeed("TEACHER_MATH_01", "teacher.math01.demo@edums.local", "Demo Mathematics Teacher 01", Role.TEACHER),
    UserSeed("TEACHER_MATH_02", "teacher.math02.demo@edums.local", "Demo Mathematics Teacher 02", Role.TEACHER),
)
STUDENTS = generate_students(12)
PARENTS: tuple[UserSeed, ...] = tuple(
    UserSeed(
        code=f"PARENT_{index:02d}",
        email=f"parent{index:02d}.demo@edums.local",
        full_name=f"Demo Parent {index:02d}",
        role=Role.PARENT,
    )
    for index in range(1, 5)
)
USERS: tuple[UserSeed, ...] = (ADMIN, *TEACHERS, *STUDENTS, *PARENTS)
