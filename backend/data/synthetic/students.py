from data.seed.records import UserSeed
from app.users.models import Role


def generate_students(count: int, *, prefix: str = "STUDENT") -> tuple[UserSeed, ...]:
    """Generate deterministic identities without Faker or random state."""
    if not 1 <= count <= 100:
        raise ValueError("count must be between 1 and 100")
    normalized = prefix.strip().upper()
    if not normalized:
        raise ValueError("prefix must be nonblank")
    return tuple(
        UserSeed(
            code=f"{normalized}_{index:02d}",
            email=f"{normalized.lower()}{index:02d}.demo@example.com",
            full_name=f"Demo Student {index:02d}",
            role=Role.STUDENT,
        )
        for index in range(1, count + 1)
    )
