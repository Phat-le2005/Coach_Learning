from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import Chapter, ProblemType, Topic
from app.subjects.models import Subject


def create_curriculum(
    session: Session, prefix: str = "SLS"
) -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Môn Học", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(
        subject_id=subject.id,
        code=f"{prefix}-CHP",
        name=f"{prefix} Chương 1",
        order_index=0,
    )
    session.add(chapter)
    session.flush()

    topic = Topic(
        chapter_id=chapter.id,
        code=f"{prefix}-TOP",
        name=f"{prefix} Chủ đề 1",
        order_index=0,
    )
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT",
        name=f"{prefix} Dạng Bài 1",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON",
        name=f"{prefix} Khái Niệm 1",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()
    return subject, chapter, topic, pt, concept
