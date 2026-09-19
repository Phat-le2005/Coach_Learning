from collections.abc import Callable

import pytest
from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.parents.models import ParentProfile, ParentStudentRelationship
from app.students.models import StudentProfile
from app.users.models import Role, User


@pytest.fixture
def profile_graph(
    db_session: Session, profile_user_factory: Callable[[Role, str], User]
) -> tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile]:
    first_parent = profile_user_factory(Role.PARENT, "parent1@example.com")
    second_parent = profile_user_factory(Role.PARENT, "parent2@example.com")
    first_student = profile_user_factory(Role.STUDENT, "student1@example.com")
    second_student = profile_user_factory(Role.STUDENT, "student2@example.com")
    p1 = db_session.scalar(select(ParentProfile).where(ParentProfile.user_id == first_parent.id))
    p2 = db_session.scalar(select(ParentProfile).where(ParentProfile.user_id == second_parent.id))
    s1 = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == first_student.id))
    s2 = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == second_student.id))
    assert p1 is not None and p2 is not None and s1 is not None and s2 is not None
    return p1, p2, s1, s2


def create_links(
    session: Session, graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile]
) -> None:
    p1, p2, s1, s2 = graph
    session.add_all([
        ParentStudentRelationship(parent_id=p1.id, student_id=s1.id, relationship_type="MOTHER"),
        ParentStudentRelationship(parent_id=p2.id, student_id=s1.id, relationship_type="FATHER"),
        ParentStudentRelationship(parent_id=p1.id, student_id=s2.id, relationship_type="GUARDIAN"),
    ])
    session.commit()


def test_many_to_many_and_inactive_relationships(
    db_session: Session, profile_graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile]
) -> None:
    create_links(db_session, profile_graph)
    p1, p2, s1, s2 = profile_graph
    assert len(s1.parent_relationships) == 2
    assert len(p1.student_relationships) == 2
    assert len(p2.student_relationships) == 1 and len(s2.parent_relationships) == 1
    assert db_session.scalar(select(func.count()).select_from(ParentStudentRelationship)) == 3
    relationship = db_session.get(ParentStudentRelationship, (p1.id, s1.id))
    assert relationship is not None and relationship.is_active is True
    relationship.is_active = False
    db_session.commit()
    active = db_session.scalars(select(ParentStudentRelationship).where(ParentStudentRelationship.is_active.is_(True))).all()
    assert len(active) == 2
    assert db_session.scalar(select(func.count()).select_from(ParentStudentRelationship)) == 3


def test_relationship_pair_cannot_be_duplicated(
    db_session: Session, profile_graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile]
) -> None:
    create_links(db_session, profile_graph)
    p1, p2, s1, s2 = profile_graph
    with pytest.raises(IntegrityError):
        db_session.execute(insert(ParentStudentRelationship).values(parent_id=p1.id, student_id=s1.id, relationship_type="OTHER"))
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(ParentStudentRelationship)) == 3


@pytest.mark.parametrize("field", ["parent_id", "student_id"])
def test_relationship_foreign_keys_use_profile_ids(
    db_session: Session, profile_graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile], field: str
) -> None:
    p1, p2, s1, s2 = profile_graph
    values = {"parent_id": p1.id, "student_id": s1.id, "relationship_type": "GUARDIAN"}
    # A User UUID does not identify a ParentProfile/StudentProfile.
    values[field] = p1.user_id if field == "parent_id" else s1.user_id
    with pytest.raises(IntegrityError):
        db_session.execute(insert(ParentStudentRelationship).values(**values))
    db_session.rollback()
    assert db_session.scalar(select(func.count()).select_from(ParentStudentRelationship)) == 0


@pytest.mark.parametrize("relationship_type", ["", "   "])
def test_relationship_type_cannot_be_empty(
    db_session: Session, profile_graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile], relationship_type: str
) -> None:
    p1, p2, s1, s2 = profile_graph
    with pytest.raises(IntegrityError):
        db_session.execute(insert(ParentStudentRelationship).values(parent_id=p1.id, student_id=s1.id, relationship_type=relationship_type))
    db_session.rollback()


@pytest.mark.parametrize("role", [Role.PARENT, Role.STUDENT])
def test_user_delete_cascades_to_profile_and_links_only(
    db_session: Session, profile_graph: tuple[ParentProfile, ParentProfile, StudentProfile, StudentProfile], role: Role
) -> None:
    create_links(db_session, profile_graph)
    p1, p2, s1, s2 = profile_graph
    deleted_user_id = p1.user_id if role == Role.PARENT else s1.user_id
    expected_parent_id = p2.id if role == Role.PARENT else p1.id
    expected_student_id = s1.id if role == Role.PARENT else s2.id
    db_session.execute(delete(User).where(User.id == deleted_user_id))
    db_session.commit()
    remaining = db_session.scalars(select(ParentStudentRelationship)).all()
    assert len(remaining) == 1
    assert remaining[0].parent_id == expected_parent_id and remaining[0].student_id == expected_student_id
    assert db_session.scalar(select(func.count()).select_from(User)) == 3
    assert db_session.scalar(select(func.count()).select_from(ParentProfile)) == (1 if role == Role.PARENT else 2)
    assert db_session.scalar(select(func.count()).select_from(StudentProfile)) == (1 if role == Role.STUDENT else 2)
