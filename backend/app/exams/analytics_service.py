from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import Chapter, ProblemType, Topic
from app.exams.models import Exam, ExamAttempt, ExamQuestion, ExamResponse
from app.exams.schemas import (
    ExamAccuracyOverTime,
    ExamAnalyticsRead,
    ExamChapterPerformance,
    ExamConceptEvidence,
    ExamDifficultyPerformance,
    ExamProblemTypePerformance,
    ExamQuestionOrderBehavior,
    ExamTimePerQuestion,
    ExamTopicPerformance,
)
from app.questions.models import Question, QuestionConcept, QuestionProblemType

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ExamAnalyticsService:
    """Comprehensive diagnostic and performance analytics engine for exam attempts.

    Metrics Computed:
    - Overall score (raw and 10.0 scale) & accuracy.
    - Chapter, Topic, and ProblemType mastery breakdown.
    - Concept evidence: maps correctness to linked concepts and prerequisite gap signals.
    - Difficulty performance: Easy, Medium, Hard performance buckets.
    - Time per question: average duration, fastest/slowest questions.
    - Unanswered questions tracking.
    - Accuracy over time: early phase vs late phase to detect fatigue or time pressure.
    - Question order behavior: sequential vs non-linear skip behavior.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def generate_analytics(self, attempt_id: UUID) -> ExamAnalyticsRead:
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.responses),
                selectinload(ExamAttempt.exam).selectinload(Exam.questions),
            )
            .where(ExamAttempt.id == attempt_id)
        )
        if attempt is None:
            raise ValueError(f"ExamAttempt {attempt_id} not found.")

        exam = attempt.exam
        exam_questions = exam.questions
        total_questions_count = len(exam_questions)
        exam_q_map: dict[UUID, ExamQuestion] = {eq.question_id: eq for eq in exam_questions}

        # Query all question details with curriculum and concept links
        q_ids = list(exam_q_map.keys())
        questions = list(
            self.session.scalars(
                select(Question)
                .options(
                    selectinload(Question.problem_type_links),
                    selectinload(Question.concept_links),
                )
                .where(Question.id.in_(q_ids))
            ).all()
        )
        questions_by_id: dict[UUID, Question] = {q.id: q for q in questions}

        # Query curriculum metadata
        pt_ids = {
            pt_link.problem_type_id
            for q in questions
            for pt_link in q.problem_type_links
        }
        problem_types = list(
            self.session.scalars(
                select(ProblemType).where(ProblemType.id.in_(list(pt_ids)))
            ).all()
        ) if pt_ids else []
        pts_by_id: dict[UUID, ProblemType] = {pt.id: pt for pt in problem_types}

        topic_ids = {pt.topic_id for pt in problem_types}
        topics = list(
            self.session.scalars(
                select(Topic).where(Topic.id.in_(list(topic_ids)))
            ).all()
        ) if topic_ids else []
        topics_by_id: dict[UUID, Topic] = {t.id: t for t in topics}

        chapter_ids = {t.chapter_id for t in topics}
        chapters = list(
            self.session.scalars(
                select(Chapter).where(Chapter.id.in_(list(chapter_ids)))
            ).all()
        ) if chapter_ids else []
        chapters_by_id: dict[UUID, Chapter] = {ch.id: ch for ch in chapters}

        # Query concepts metadata and prerequisite relations
        concept_ids = {
            c_link.concept_id
            for q in questions
            for c_link in q.concept_links
        }
        concepts = list(
            self.session.scalars(
                select(Concept).where(Concept.id.in_(list(concept_ids)))
            ).all()
        ) if concept_ids else []
        concepts_by_id: dict[UUID, Concept] = {c.id: c for c in concepts}

        prereq_concept_ids = set(
            self.session.scalars(
                select(ConceptRelation.source_concept_id).where(
                    ConceptRelation.source_concept_id.in_(list(concept_ids)),
                    ConceptRelation.relation_type == RelationType.PREREQUISITE,
                )
            ).all()
        ) if concept_ids else set()

        # Map responses
        responses_by_qid: dict[UUID, ExamResponse] = {
            r.question_id: r for r in attempt.responses
        }

        # Basic counters
        correct_count = 0
        incorrect_count = 0
        unanswered_count = 0
        unanswered_ids: list[UUID] = []

        total_points = sum(eq.points for eq in exam_questions)
        earned_score = 0.0

        for qid, eq in exam_q_map.items():
            resp = responses_by_qid.get(qid)
            if resp is None or not resp.student_answer:
                unanswered_count += 1
                unanswered_ids.append(qid)
            elif resp.is_correct:
                correct_count += 1
                earned_score += resp.score_awarded if resp.score_awarded is not None else eq.points
            else:
                incorrect_count += 1

        accuracy = (correct_count / total_questions_count) if total_questions_count > 0 else 0.0
        final_score = attempt.score if attempt.score is not None else earned_score
        score_10 = round((final_score / total_points * 10.0), 2) if total_points > 0 else 0.0

        # ----------------------------------------------------------------------
        # 1. Chapter, Topic, ProblemType Performance
        # ----------------------------------------------------------------------
        chap_stats: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0, "name": ""}
        )
        topic_stats: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0, "name": "", "chapter_name": ""}
        )
        pt_stats: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0, "name": "", "topic_name": ""}
        )

        for qid, eq in exam_q_map.items():
            q = questions_by_id.get(qid)
            if not q:
                continue
            resp = responses_by_qid.get(qid)
            is_c = bool(resp and resp.is_correct)
            awarded = resp.score_awarded if resp and resp.score_awarded is not None else (eq.points if is_c else 0.0)

            for pt_link in q.problem_type_links:
                pt = pts_by_id.get(pt_link.problem_type_id)
                if not pt:
                    continue
                # ProblemType
                t = topics_by_id.get(pt.topic_id)
                ch = chapters_by_id.get(t.chapter_id) if t else None

                p_st = pt_stats[pt.id]
                p_st["name"] = pt.name
                p_st["topic_name"] = t.name if t else ""
                p_st["total"] += 1
                if is_c:
                    p_st["correct"] += 1
                    p_st["score_earned"] += awarded
                p_st["max_score"] += eq.points

                # Topic
                if t:
                    t_st = topic_stats[t.id]
                    t_st["name"] = t.name
                    t_st["chapter_name"] = ch.name if ch else ""
                    t_st["total"] += 1
                    if is_c:
                        t_st["correct"] += 1
                        t_st["score_earned"] += awarded
                    t_st["max_score"] += eq.points

                    # Chapter
                    if ch:
                        c_st = chap_stats[ch.id]
                        c_st["name"] = ch.name
                        c_st["total"] += 1
                        if is_c:
                            c_st["correct"] += 1
                            c_st["score_earned"] += awarded
                        c_st["max_score"] += eq.points

        chapter_performance = [
            ExamChapterPerformance(
                chapter_id=cid,
                chapter_name=data["name"],
                total_questions=data["total"],
                correct_count=data["correct"],
                accuracy=round(data["correct"] / data["total"], 2) if data["total"] > 0 else 0.0,
                score_earned=round(data["score_earned"], 2),
                max_score=round(data["max_score"], 2),
            )
            for cid, data in chap_stats.items()
        ]

        topic_performance = [
            ExamTopicPerformance(
                topic_id=tid,
                topic_name=data["name"],
                chapter_name=data["chapter_name"],
                total_questions=data["total"],
                correct_count=data["correct"],
                accuracy=round(data["correct"] / data["total"], 2) if data["total"] > 0 else 0.0,
                score_earned=round(data["score_earned"], 2),
                max_score=round(data["max_score"], 2),
            )
            for tid, data in topic_stats.items()
        ]

        problem_type_performance = [
            ExamProblemTypePerformance(
                problem_type_id=pid,
                problem_type_name=data["name"],
                topic_name=data["topic_name"],
                total_questions=data["total"],
                correct_count=data["correct"],
                accuracy=round(data["correct"] / data["total"], 2) if data["total"] > 0 else 0.0,
                score_earned=round(data["score_earned"], 2),
                max_score=round(data["max_score"], 2),
            )
            for pid, data in pt_stats.items()
        ]

        # ----------------------------------------------------------------------
        # 2. Concept Evidence (Prerequisite Diagnostics)
        # ----------------------------------------------------------------------
        concept_stats: dict[UUID, dict[str, Any]] = defaultdict(
            lambda: {"total": 0, "correct": 0, "name": "", "is_prereq": False}
        )
        for qid, eq in exam_q_map.items():
            q = questions_by_id.get(qid)
            if not q:
                continue
            resp = responses_by_qid.get(qid)
            is_c = bool(resp and resp.is_correct)
            for c_link in q.concept_links:
                c = concepts_by_id.get(c_link.concept_id)
                if not c:
                    continue
                c_st = concept_stats[c.id]
                c_st["name"] = c.name
                c_st["is_prereq"] = c.id in prereq_concept_ids
                c_st["total"] += 1
                if is_c:
                    c_st["correct"] += 1

        concept_evidence = []
        for cid, data in concept_stats.items():
            acc = round(data["correct"] / data["total"], 2) if data["total"] > 0 else 0.0
            if acc >= 0.75:
                signal = "STRONG"
            elif data["is_prereq"] and acc < 0.50:
                signal = "PREREQUISITE_GAP"
            else:
                signal = "NEEDS_PRACTICE"

            concept_evidence.append(
                ExamConceptEvidence(
                    concept_id=cid,
                    concept_name=data["name"],
                    is_prerequisite=data["is_prereq"],
                    questions_tested=data["total"],
                    correct_count=data["correct"],
                    accuracy=acc,
                    diagnostic_signal=signal,
                )
            )

        # ----------------------------------------------------------------------
        # 3. Difficulty Performance (EASY, MEDIUM, HARD)
        # ----------------------------------------------------------------------
        diff_buckets: dict[str, dict[str, Any]] = {
            "EASY": {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0},
            "MEDIUM": {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0},
            "HARD": {"total": 0, "correct": 0, "score_earned": 0.0, "max_score": 0.0},
        }

        for qid, eq in exam_q_map.items():
            q = questions_by_id.get(qid)
            diff = q.difficulty if q else 0.5
            bucket = "EASY" if diff < 0.35 else ("MEDIUM" if diff < 0.70 else "HARD")
            resp = responses_by_qid.get(qid)
            is_c = bool(resp and resp.is_correct)
            awarded = resp.score_awarded if resp and resp.score_awarded is not None else (eq.points if is_c else 0.0)

            diff_buckets[bucket]["total"] += 1
            if is_c:
                diff_buckets[bucket]["correct"] += 1
                diff_buckets[bucket]["score_earned"] += awarded
            diff_buckets[bucket]["max_score"] += eq.points

        difficulty_performance = [
            ExamDifficultyPerformance(
                difficulty_level=level,
                total_questions=data["total"],
                correct_count=data["correct"],
                accuracy=round(data["correct"] / data["total"], 2) if data["total"] > 0 else 0.0,
                score_earned=round(data["score_earned"], 2),
                max_score=round(data["max_score"], 2),
            )
            for level, data in diff_buckets.items()
            if data["total"] > 0
        ]

        # ----------------------------------------------------------------------
        # 4. Time per Question
        # ----------------------------------------------------------------------
        times: list[tuple[UUID, float]] = []
        for resp in attempt.responses:
            if resp.response_time_seconds and resp.response_time_seconds > 0:
                times.append((resp.question_id, resp.response_time_seconds))

        total_recorded_time = sum(t for _, t in times)
        avg_time = round(total_recorded_time / len(times), 1) if times else 0.0
        fastest_qid = min(times, key=lambda x: x[1])[0] if times else None
        slowest_qid = max(times, key=lambda x: x[1])[0] if times else None

        time_per_question = ExamTimePerQuestion(
            average_seconds_per_question=avg_time,
            total_time_seconds=int(round(total_recorded_time)),
            fastest_question_id=fastest_qid,
            slowest_question_id=slowest_qid,
        )

        # ----------------------------------------------------------------------
        # 5. Accuracy Over Time (Fatigue / Time Pressure Analysis)
        # ----------------------------------------------------------------------
        # Chronologically ordered answered responses
        answered_responses = [
            r for r in attempt.responses if r.student_answer and r.answered_at
        ]
        answered_responses.sort(key=lambda r: _as_utc(r.answered_at))

        if len(answered_responses) >= 2:
            mid = len(answered_responses) // 2
            first_half = answered_responses[:mid]
            second_half = answered_responses[mid:]

            first_acc = sum(1 for r in first_half if r.is_correct) / len(first_half)
            second_acc = sum(1 for r in second_half if r.is_correct) / len(second_half)

            pressure_detected = (first_acc - second_acc) >= 0.25
            if pressure_detected:
                summary = "Phát hiện dấu hiệu áp lực thời gian hoặc giảm sút tập trung ở nửa sau bài thi."
            elif second_acc > first_acc:
                summary = "Học sinh bắt nhịp tốt, duy trì phong độ cao hơn ở giai đoạn sau của bài thi."
            else:
                summary = "Độ chính xác tương đối đồng đều xuyên suốt thời gian làm bài."
        else:
            first_acc = accuracy
            second_acc = accuracy
            pressure_detected = False
            summary = "Chưa đủ dữ liệu chuỗi thời gian để phát hiện biến động độ chính xác."

        accuracy_over_time = ExamAccuracyOverTime(
            first_half_accuracy=round(first_acc, 2),
            second_half_accuracy=round(second_acc, 2),
            time_pressure_detected=pressure_detected,
            summary=summary,
        )

        # ----------------------------------------------------------------------
        # 6. Question Order Behavior
        # ----------------------------------------------------------------------
        # Check order of answered questions relative to exam question order_index
        ordered_by_sequence = sorted(
            [r for r in attempt.responses if r.order_answered > 0],
            key=lambda r: r.order_answered,
        )

        sequence_indices = [
            exam_q_map[r.question_id].order_index
            for r in ordered_by_sequence
            if r.question_id in exam_q_map
        ]

        is_sequential = True
        skip_count = 0
        for i in range(1, len(sequence_indices)):
            if sequence_indices[i] != sequence_indices[i - 1] + 1:
                is_sequential = False
                skip_count += 1

        if not sequence_indices or is_sequential:
            behavior_summary = "Làm bài tuần tự theo đúng thứ tự câu hỏi trong đề."
        else:
            behavior_summary = f"Làm bài linh hoạt có chọn lọc, nhảy cóc {skip_count} lần để giải quyết câu dễ trước."

        question_order_behavior = ExamQuestionOrderBehavior(
            is_sequential=is_sequential,
            skip_count=skip_count,
            answered_order_sequence=sequence_indices,
            behavior_summary=behavior_summary,
        )

        return ExamAnalyticsRead(
            attempt_id=attempt.id,
            exam_id=exam.id,
            student_id=attempt.student_id,
            exam_title=exam.title,
            exam_type=exam.exam_type,
            duration_seconds=attempt.duration_seconds,
            score=round(final_score, 2),
            score_10=score_10,
            total_points=round(total_points, 2),
            accuracy=round(accuracy, 4),
            total_questions=total_questions_count,
            correct_count=correct_count,
            incorrect_count=incorrect_count,
            unanswered_count=unanswered_count,
            unanswered_question_ids=unanswered_ids,
            chapter_performance=chapter_performance,
            topic_performance=topic_performance,
            problem_type_performance=problem_type_performance,
            concept_evidence=concept_evidence,
            difficulty_performance=difficulty_performance,
            time_per_question=time_per_question,
            accuracy_over_time=accuracy_over_time,
            question_order_behavior=question_order_behavior,
        )
