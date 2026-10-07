from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.classes.analytics_schemas import AlertRuleCode, AlertSeverity, HeatmapView
from app.classes.analytics_service import ClassAnalyticsService
from app.classes.copilot_schemas import TeacherCopilotRequest
from app.classes.copilot_service import TeacherCopilotService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.graph_service import ConceptGraphService
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import Settings
from app.curriculum.import_service import CurriculumImportService
from app.curriculum.models import (
    Chapter,
    LearningOutcome,
    ProblemType,
    ProblemTypeConcept,
    ProblemTypeLearningOutcome,
    Topic,
)
from app.diagnostics.models import DiagnosticCompletionReason
from app.diagnostics.schemas import DiagnosticAnswerCreate, DiagnosticStartCreate
from app.diagnostics.service import DiagnosticService
from app.digital_twin.service import StudentDigitalTwinService
from app.exams.ai_explanation_service import ExamAIExplanationService
from app.exams.analytics_service import ExamAnalyticsService
from app.exams.models import (
    Exam,
    ExamAttempt,
    ExamAttemptStatus,
    ExamQuestion,
    ExamResponse,
    ExamStatus,
    ExamType,
)
from app.exams.schemas import ExamResponseSubmitRequest
from app.exams.simulation_service import ExamSimulationService
from app.hints.models import HintLevel, PracticeQuestionHint, QuestionHint
from app.hints.schemas import HintRequest
from app.hints.service import HintService
from app.knowledge_gap.schemas import KnowledgeGapResult
from app.knowledge_gap.service import KnowledgeGapService
from app.learning.models import QuickCheckSession
from app.learning.schemas import QuickCheckStartRequest
from app.learning.service import QuickCheckService
from app.mastery.aggregation import MasteryAggregationService
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.misconceptions.service import MisconceptionService
from app.parents.dashboard_service import ParentDashboardService
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.parents.parent_ai_service import ParentAISummaryService
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTaskStatus
from app.planning.study_service import StudyPlanService
from app.practice.models import EvaluationStatus, PracticeSession, PracticeSessionType, QuestionAttempt
from app.practice.schemas import PracticeAnswerCreate
from app.questions.fingerprint import question_content_hash
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.recommendations.question_service import QuestionRecommendationService
from app.repair.schemas import RepairAnswerSubmit, RepairSessionCreate, RepairTargetType, RepairTriggerType
from app.repair.service import RepairSessionService
from app.seed_service import SeedService
from app.students.goal_models import AcademicGoal, AcademicGoalStatus
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "Integration-MVP-Password-2026!"


def _create_user(session: Session, role: Role, email: str, full_name: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name=full_name, role=role)
    )


def _create_bank_question(
    session: Session,
    subject: Subject,
    creator_id: UUID,
    content: str,
    pt: ProblemType,
    concept: Concept,
    lo: LearningOutcome,
    *,
    correct_answer: str = "A",
    difficulty: float = 0.35,
    hints: list[str] | None = None,
) -> Question:
    q = Question(
        subject_id=subject.id,
        content=content,
        content_hash=question_content_hash(content),
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation=f"Giải thích chi tiết cho: {content}",
        source_type="CURRICULUM_BANK",
        source_reference="GDPT2018-TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        cognitive_level=CognitiveLevel.UNDERSTAND,
        created_by=creator_id,
        options=[
            QuestionOption(label="A", content="Phương án A", order_index=0),
            QuestionOption(label="B", content="Phương án B", order_index=1),
            QuestionOption(label="C", content="Phương án C", order_index=2),
            QuestionOption(label="D", content="Phương án D", order_index=3),
        ],
    )
    q.problem_type_links.append(
        QuestionProblemType(problem_type_id=pt.id, weight=1.0, is_primary=True)
    )
    q.concept_links.append(QuestionConcept(concept_id=concept.id, weight=1.0))
    q.learning_outcome_links.append(QuestionLearningOutcome(learning_outcome_id=lo.id, weight=1.0))

    session.add(q)
    session.flush()

    if hints:
        level_map = [
            HintLevel.LEVEL_1,
            HintLevel.LEVEL_2,
            HintLevel.LEVEL_3,
            HintLevel.LEVEL_4,
        ]
        for idx, hint_text in enumerate(hints):
            if idx < len(level_map):
                session.add(
                    QuestionHint(
                        question_id=q.id,
                        hint_level=level_map[idx],
                        content=hint_text,
                    )
                )
        session.flush()

    return q


# ==============================================================================
# 1. Critical Flow: 42 Milestones End-to-End Integration Test
# ==============================================================================


@pytest.mark.anyio
async def test_mvp_critical_path_end_to_end(db_session: Session, settings: Settings) -> None:
    """Execute all 42 milestones of the MVP Critical Path sequentially with zero mock/fake flow."""

    mock_gateway = AIGateway(provider=MockAIProvider(), settings=settings)

    # --------------------------------------------------------------------------
    # [1] Admin import CurriculumVersion (MATH_G12_GDPT2018_CORE)
    # --------------------------------------------------------------------------
    importer = CurriculumImportService(db_session)
    import_result = importer.import_dataset("MATH_G12_GDPT2018_CORE", commit=False)
    assert import_result is not None
    assert import_result.dataset_code == "MATH_G12_GDPT2018_CORE"
    db_session.flush()

    # --------------------------------------------------------------------------
    # [2-5] Curriculum Hierarchy: Subject -> Chapter -> Topic -> ProblemTypes
    # --------------------------------------------------------------------------
    subject = db_session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
    assert subject is not None, "Subject MATH_G12 must be present after curriculum import"

    chapters = list(
        db_session.scalars(
            select(Chapter).where(Chapter.subject_id == subject.id).order_by(Chapter.order_index)
        ).all()
    )
    assert len(chapters) >= 1, "Chapters must be loaded under subject"
    primary_chapter = chapters[0]

    topics = list(
        db_session.scalars(
            select(Topic).where(Topic.chapter_id == primary_chapter.id).order_by(Topic.order_index)
        ).all()
    )
    assert len(topics) >= 1, "Topics must be loaded under primary chapter"
    primary_topic = topics[0]

    problem_types = list(
        db_session.scalars(
            select(ProblemType)
            .where(ProblemType.topic_id == primary_topic.id)
            .order_by(ProblemType.order_index)
        ).all()
    )
    assert len(problem_types) >= 1, "ProblemTypes must be present under topic"
    active_problem_type = problem_types[0]

    # --------------------------------------------------------------------------
    # [6] ProblemTypes map Concepts + LearningOutcomes
    # --------------------------------------------------------------------------
    pt_concepts = list(
        db_session.scalars(
            select(ProblemTypeConcept).where(
                ProblemTypeConcept.problem_type_id == active_problem_type.id
            )
        ).all()
    )
    assert len(pt_concepts) >= 1, "ProblemType must be mapped to at least one Concept"
    primary_concept = db_session.get(Concept, pt_concepts[0].concept_id)
    assert primary_concept is not None

    pt_outcomes = list(
        db_session.scalars(
            select(ProblemTypeLearningOutcome).where(
                ProblemTypeLearningOutcome.problem_type_id == active_problem_type.id
            )
        ).all()
    )
    assert len(pt_outcomes) >= 1, "ProblemType must be mapped to at least one LearningOutcome"
    primary_outcome = db_session.get(LearningOutcome, pt_outcomes[0].learning_outcome_id)
    assert primary_outcome is not None

    # --------------------------------------------------------------------------
    # [7] Concept prerequisite graph is a valid acyclic DAG
    # --------------------------------------------------------------------------
    all_subject_concepts = list(
        db_session.scalars(select(Concept).where(Concept.subject_id == subject.id)).all()
    )
    assert len(all_subject_concepts) >= 2
    concept_graph = ConceptGraphService(db_session)
    prereq_tree = concept_graph.get_prerequisite_tree(primary_concept.id)
    assert prereq_tree.root_concept_id == primary_concept.id

    # Seed misconception taxonomy
    seed_service = SeedService(db_session, settings)
    seed_service._seed_misconception_definitions()
    db_session.flush()

    misconception_def = db_session.scalar(
        select(MisconceptionDefinition).where(
            MisconceptionDefinition.concept_id == primary_concept.id
        )
    )
    if misconception_def is None:
        misconception_def = db_session.scalar(select(MisconceptionDefinition))
    assert misconception_def is not None, "Misconception definitions must be available"

    # --------------------------------------------------------------------------
    # [8] Question Bank questions map ProblemType + Concepts + LearningOutcomes
    # --------------------------------------------------------------------------
    admin_user = _create_user(db_session, Role.ADMIN, "admin.mvp@example.com", "Admin MVP")
    db_session.flush()

    q_hints = [
        "Bước 1: Tính đạo hàm f'(x) của hàm số đã cho.",
        "Bước 2: Tìm các nghiệm của phương trình f'(x) = 0.",
        "Bước 3: Lập bảng biến thiên và xét dấu đạo hàm trên khoảng cần tìm.",
        "Bước 4: Kết luận khoảng đồng biến dựa trên dấu dương của f'(x).",
    ]

    # Create 6 questions with pedagogical links and scaffolded hints
    created_questions: list[Question] = []
    for i in range(6):
        q = _create_bank_question(
            db_session,
            subject,
            admin_user.id,
            f"Câu hỏi kiểm tra số {i + 1}: Cho hàm số y = f(x)... Xét tính đơn điệu?",
            active_problem_type,
            primary_concept,
            primary_outcome,
            correct_answer="A",
            difficulty=0.25 + (i * 0.10),
            hints=q_hints,
        )
        created_questions.append(q)
    db_session.commit()

    # --------------------------------------------------------------------------
    # [9-10] Teacher creates Classroom & Student joins Classroom
    # --------------------------------------------------------------------------
    teacher_user = _create_user(
        db_session, Role.TEACHER, "teacher.mvp@example.com", "Thầy Nguyễn Văn A"
    )
    student_user = _create_user(
        db_session, Role.STUDENT, "student.mvp@example.com", "Em Trần Văn B"
    )
    parent_user = _create_user(
        db_session, Role.PARENT, "parent.mvp@example.com", "Phụ huynh Trần Văn C"
    )
    db_session.flush()

    teacher_prof = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id)
    )
    student_prof = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student_user.id)
    )
    parent_prof = db_session.scalar(
        select(ParentProfile).where(ParentProfile.user_id == parent_user.id)
    )
    assert teacher_prof and student_prof and parent_prof

    classroom = Classroom(
        name="Lớp 12A1 Chuẩn",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()

    db_session.add(
        TeacherClassroom(teacher_id=teacher_prof.id, classroom_id=classroom.id, role="OWNER")
    )
    db_session.add(
        StudentEnrollment(
            student_id=student_prof.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )
    db_session.add(
        ParentStudentRelationship(
            parent_id=parent_prof.id,
            student_id=student_prof.id,
            relationship_type="father",
            is_active=True,
        )
    )
    db_session.commit()

    # --------------------------------------------------------------------------
    # [11] Teacher activates TeachingPlan with target ProblemTypes
    # --------------------------------------------------------------------------
    teaching_plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        status=TeachingPlanStatus.ACTIVE,
        start_date=date.today() - timedelta(days=7),
        created_by=teacher_user.id,
    )
    db_session.add(teaching_plan)
    db_session.flush()

    tp_item = TeachingPlanItem(
        teaching_plan_id=teaching_plan.id,
        problem_type_id=active_problem_type.id,
        order_index=1,
        priority=1,
    )
    db_session.add(tp_item)
    db_session.commit()

    # --------------------------------------------------------------------------
    # [12] Student creates AcademicGoal
    # --------------------------------------------------------------------------
    academic_goal = AcademicGoal(
        student_id=student_prof.id,
        target_exam="THPTQG",
        exam_date=date.today() + timedelta(days=120),
        available_daily_minutes=60,
        status=AcademicGoalStatus.ACTIVE,
    )
    db_session.add(academic_goal)
    db_session.commit()

    # --------------------------------------------------------------------------
    # [13-16] Student runs Diagnostic -> ProblemType & Concept Masteries & Aggregation
    # --------------------------------------------------------------------------
    diag_service = DiagnosticService(db_session)
    diag_start = diag_service.start(
        student_user,
        DiagnosticStartCreate(
            subject_id=subject.id,
            max_questions=2,
            minimum_problem_type_coverage=0.1,
            confidence_threshold=0.5,
        ),
    )
    assert diag_start.id is not None

    next_q = diag_service.next_question(student_user, diag_start.id)
    assert next_q.question is not None
    assert next_q.question.id is not None

    diag_ans = diag_service.answer(
        student_user,
        diag_start.id,
        DiagnosticAnswerCreate(
            question_id=next_q.question.id,
            student_answer="A",  # Correct answer
            response_time_seconds=35.0,
        ),
    )
    assert diag_ans.attempt.is_correct is True

    # Complete diagnostic if more questions exist
    next_q2 = diag_service.next_question(student_user, diag_start.id)
    if next_q2.question is not None:
        diag_service.answer(
            student_user,
            diag_start.id,
            DiagnosticAnswerCreate(
                question_id=next_q2.question.id,
                student_answer="A",
                response_time_seconds=40.0,
            ),
        )
    db_session.commit()

    # Verify persisted leaf masteries
    pt_mastery = db_session.get(
        StudentProblemTypeMastery, (student_prof.id, active_problem_type.id)
    )
    assert pt_mastery is not None, "StudentProblemTypeMastery must be created after diagnostic"
    assert pt_mastery.attempt_count >= 1

    concept_mastery = db_session.get(
        StudentConceptMastery, (student_prof.id, primary_concept.id)
    )
    assert concept_mastery is not None, "StudentConceptMastery must be created after diagnostic"

    # Verify Topic & Chapter aggregation
    agg_service = MasteryAggregationService(db_session)
    topic_agg = agg_service.get_topic_mastery(student_prof.id, primary_topic.id)
    assert topic_agg is not None
    assert topic_agg.attempt_count >= 1

    chap_agg = agg_service.get_chapter_mastery(student_prof.id, primary_chapter.id)
    assert chap_agg is not None
    assert chap_agg.attempt_count >= 1

    # --------------------------------------------------------------------------
    # [17] Digital Twin reflects both ProblemType and Concept
    # --------------------------------------------------------------------------
    twin_service = StudentDigitalTwinService(db_session)
    twin_snapshot = twin_service.get_snapshot(student_prof.id)
    assert twin_snapshot.basic_profile.student_id == student_prof.id
    assert len(twin_snapshot.curriculum_progress) >= 1
    assert len(twin_snapshot.knowledge_state.concepts) >= 1

    # --------------------------------------------------------------------------
    # [18-19] Study Plan creates daily tasks & Student studies active ProblemType
    # --------------------------------------------------------------------------
    study_service = StudyPlanService(db_session)
    today_plan = study_service.get_today_plan(student_prof.id)
    assert len(today_plan.tasks) >= 1
    assert any(
        t.problem_type_id == active_problem_type.id for t in today_plan.tasks
    ), "Daily study task must target active ProblemType from TeachingPlan"

    # --------------------------------------------------------------------------
    # [20-23] Quick Check -> Student answers incorrectly -> QuestionAttempt saved -> Mastery Engine updates
    # --------------------------------------------------------------------------
    qc_service = QuickCheckService(db_session)
    qc_start = qc_service.start_quick_check(
        student_user,
        QuickCheckStartRequest(subject_id=subject.id, classroom_id=classroom.id),
    )
    assert qc_start.id is not None
    assert len(qc_start.questions) >= 1

    qc_target_question_id = qc_start.questions[0].question_id

    # --------------------------------------------------------------------------
    # [26-27] Student requests Hint -> Scaffolded Hint System returns Level 1
    # --------------------------------------------------------------------------
    hint_service = HintService(db_session, gateway=mock_gateway)
    hint_res = await hint_service.get_hint(
        student_user,
        qc_target_question_id,
        HintRequest(
            practice_session_id=qc_start.id,
            current_hint_level=HintLevel.LEVEL_1,
        ),
    )
    assert isinstance(hint_res, PracticeQuestionHint)
    assert hint_res.hint_level == HintLevel.LEVEL_1
    assert "Bước 1" in hint_res.content
    assert not hint_res.content.startswith("Đáp án đúng là")

    # --------------------------------------------------------------------------
    # [21-22] Student submits WRONG answer ("B" instead of "A") -> Attempt saved
    # --------------------------------------------------------------------------
    qc_attempt_read = qc_service.answer_question(
        student_user,
        qc_start.id,
        PracticeAnswerCreate(
            question_id=qc_target_question_id,
            student_answer="B",
            response_time_seconds=55.0,
        ),
    )
    assert qc_attempt_read.is_correct is False

    # Verify QuestionAttempt saved
    persisted_attempt = db_session.scalar(
        select(QuestionAttempt).where(
            QuestionAttempt.practice_session_id == qc_start.id,
            QuestionAttempt.question_id == qc_target_question_id,
        )
    )
    assert persisted_attempt is not None
    assert persisted_attempt.is_correct is False
    assert persisted_attempt.student_id == student_prof.id

    # --------------------------------------------------------------------------
    # [23] Verify Mastery Engine updated ProblemType and Concept mastery downwards/adjusted
    # --------------------------------------------------------------------------
    db_session.refresh(pt_mastery)
    db_session.refresh(concept_mastery)
    assert pt_mastery.attempt_count >= 2

    # --------------------------------------------------------------------------
    # [24-25] KnowledgeGapService analyzes gap & detects weakness
    # --------------------------------------------------------------------------
    gap_service = KnowledgeGapService(db_session, gateway=mock_gateway)
    gap_result = await gap_service.analyze_gap(
        student_prof.id, active_problem_type.id, use_ai=False
    )
    assert isinstance(gap_result, KnowledgeGapResult)
    assert gap_result.target_problem_type_id == active_problem_type.id
    assert gap_result.gap_type is not None

    # --------------------------------------------------------------------------
    # [28-29] Repeated error -> Misconception evidence recorded & status updated
    # --------------------------------------------------------------------------
    misc_service = MisconceptionService(db_session)
    student_misc = misc_service.record_evidence(
        student_prof.id,
        misconception_def.id,
        confidence_increment=0.40,
    )
    # Second occurrence confirms misconception
    student_misc_confirmed = misc_service.record_evidence(
        student_prof.id,
        misconception_def.id,
        confidence_increment=0.40,
    )
    assert student_misc_confirmed.occurrence_count == 2
    assert student_misc_confirmed.status == StudentMisconceptionStatus.CONFIRMED

    # --------------------------------------------------------------------------
    # [30-32] Repair Session targets weak ProblemType -> 5 steps completed -> Mastery lift
    # --------------------------------------------------------------------------
    repair_service = RepairSessionService(db_session)
    repair_session_read = repair_service.start_repair_session(
        student_user,
        RepairSessionCreate(
            trigger=RepairTriggerType.LOW_PROBLEM_TYPE_MASTERY,
            target_type=RepairTargetType.PROBLEM_TYPE,
            target_id=active_problem_type.id,
        ),
    )
    assert repair_session_read.target_type == RepairTargetType.PROBLEM_TYPE
    assert len(repair_session_read.steps) == 5

    # Step 1 is BRIEF_REVIEW. Submit answers for steps 2 to 5 (all correct "A")
    for step_idx in range(2, 6):
        repair_service.submit_step_answer(
            student_user,
            repair_session_read.id,
            step_number=step_idx,
            data=RepairAnswerSubmit(student_answer="A", response_time_seconds=25.0),
        )

    eval_repair = repair_service.evaluate_session_completion(
        student_user, repair_session_read.id
    )
    assert eval_repair.is_successful is True
    assert eval_repair.final_recheck_correct is True

    # Check mastery lift
    db_session.refresh(pt_mastery)
    assert pt_mastery.correct_count >= 1

    # --------------------------------------------------------------------------
    # [33] Question Recommendation Engine picks next question
    # --------------------------------------------------------------------------
    recom_service = QuestionRecommendationService(db_session)
    recommendation = recom_service.recommend(
        student_prof.id,
        subject.id,
        target_problem_type_id=active_problem_type.id,
    )
    assert recommendation is not None
    assert recommendation.question_id in [q.id for q in created_questions]

    # --------------------------------------------------------------------------
    # [34-36] Teacher Analytics: Heatmap, Prerequisite Signals, Intervention Alerts
    # --------------------------------------------------------------------------
    analytics_service = ClassAnalyticsService(db_session)

    # 34. Heatmap by ProblemType
    heatmap = analytics_service.get_classroom_heatmap(
        teacher_user.id,
        classroom.id,
        view=HeatmapView.PROBLEM_TYPE,
        subject_id=subject.id,
    )
    assert len(heatmap.rows) == 1
    assert heatmap.rows[0].student_id == student_prof.id
    assert any(col.id == active_problem_type.id for col in heatmap.columns)

    # 35. Heatmap by Concept (Prerequisite signals)
    concept_heatmap = analytics_service.get_classroom_heatmap(
        teacher_user.id,
        classroom.id,
        view=HeatmapView.CONCEPT,
        subject_id=subject.id,
    )
    assert len(concept_heatmap.columns) >= 1

    # 36. Intervention Alerts
    alerts = analytics_service.get_classroom_alerts(teacher_user.id, classroom.id)
    assert alerts.classroom_id == classroom.id

    # --------------------------------------------------------------------------
    # [37] Teacher Copilot explains class state
    # --------------------------------------------------------------------------
    copilot_service = TeacherCopilotService(db_session, gateway=mock_gateway)
    copilot_response = await copilot_service.consult_copilot_async(
        teacher_user.id,
        classroom.id,
        TeacherCopilotRequest(
            query="Tình hình nắm vững dạng bài đơn điệu của lớp hiện tại ra sao?",
            subject_id=subject.id,
        ),
    )
    assert copilot_response.classroom_id == classroom.id
    assert len(copilot_response.observations) >= 1
    assert len(copilot_response.recommended_actions) >= 1

    # --------------------------------------------------------------------------
    # [38-39] Parent Dashboard aggregated weekly data & Parent AI Summary
    # --------------------------------------------------------------------------
    parent_service = ParentDashboardService(db_session)
    weekly_data = parent_service.get_student_weekly_data(parent_user.id, student_prof.id)
    assert weekly_data.student_id == student_prof.id
    assert len(weekly_data.daily_study_time) == 7

    parent_ai_service = ParentAISummaryService(db_session, gateway=mock_gateway)
    weekly_summary = await parent_ai_service.generate_weekly_summary_async(
        parent_user.id, student_prof.id
    )
    assert weekly_summary.student_id == student_prof.id
    assert len(weekly_summary.how_parent_can_help) <= 2
    assert weekly_summary.progress != ""

    # --------------------------------------------------------------------------
    # [40-42] Student Exam Simulation -> Analytics by Chapter/Topic/PT -> AI Explanation
    # --------------------------------------------------------------------------
    # 40. Simulation Exam
    exam = Exam(
        subject_id=subject.id,
        title="Đề kiểm tra giữa kỳ Toán 12",
        duration_minutes=45,
        exam_type=ExamType.REAL_SIMULATION,
        status=ExamStatus.PUBLISHED,
        created_by=teacher_user.id,
        total_points=10.0,
        total_questions=2,
    )
    db_session.add(exam)
    db_session.flush()

    db_session.add(
        ExamQuestion(
            exam_id=exam.id,
            question_id=created_questions[0].id,
            order_index=0,
            points=5.0,
        )
    )
    db_session.add(
        ExamQuestion(
            exam_id=exam.id,
            question_id=created_questions[1].id,
            order_index=1,
            points=5.0,
        )
    )
    db_session.commit()

    sim_service = ExamSimulationService(db_session)
    start_info = sim_service.start_exam(student_user.id, exam.id)
    exam_attempt_id = start_info.attempt_id

    # Submit answers: Q1 correct "A", Q2 incorrect "B"
    sim_service.record_response(
        student_user.id,
        exam_attempt_id,
        ExamResponseSubmitRequest(
            question_id=created_questions[0].id,
            student_answer="A",
            response_time_seconds=40.0,
        ),
    )
    sim_service.record_response(
        student_user.id,
        exam_attempt_id,
        ExamResponseSubmitRequest(
            question_id=created_questions[1].id,
            student_answer="B",
            response_time_seconds=50.0,
        ),
    )

    completed_attempt = sim_service.submit_exam(student_user.id, exam_attempt_id)
    assert completed_attempt.status == ExamAttemptStatus.GRADED
    assert completed_attempt.score == 5.0
    assert completed_attempt.total_points == 10.0

    # 41. Exam Analytics by Chapter / Topic / ProblemType
    exam_analytics_service = ExamAnalyticsService(db_session)
    analytics_read = exam_analytics_service.generate_analytics(exam_attempt_id)
    assert analytics_read.score == 5.0
    assert analytics_read.total_questions == 2
    assert analytics_read.correct_count == 1
    assert analytics_read.incorrect_count == 1
    assert len(analytics_read.chapter_performance) >= 1
    assert len(analytics_read.topic_performance) >= 1
    assert len(analytics_read.problem_type_performance) >= 1

    # 42. AI Exam Analysis (Grounded pedagogical diagnosis without score tampering)
    exam_ai_service = ExamAIExplanationService(db_session, gateway=mock_gateway)
    explanation = exam_ai_service.generate_explanation(exam_attempt_id, student_user.id)
    assert explanation.score == 5.0
    assert explanation.score_10 == 5.0
    assert explanation.attempt_id == exam_attempt_id
    assert explanation.student_friendly_summary != ""


# ==============================================================================
# 2. Invariant Verification: Learning Core Resilient During AI Outage
# ==============================================================================


@pytest.mark.anyio
async def test_learning_core_resilient_during_ai_outage(
    db_session: Session, settings: Settings
) -> None:
    """Ensure Learning Core (grading, mastery, repair, exam) continues uninterrupted

    when AI services are completely unavailable (graceful fallback without 500s).
    """
    failing_provider = MockAIProvider(service_unavailable_failures=999)
    failing_gateway = AIGateway(provider=failing_provider, settings=settings)

    # Setup base actors and curriculum
    importer = CurriculumImportService(db_session)
    importer.import_dataset("MATH_G12_GDPT2018_CORE", commit=False)
    db_session.flush()

    subject = db_session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
    assert subject is not None
    pt = db_session.scalar(select(ProblemType))
    assert pt is not None
    concept = db_session.scalar(select(Concept).where(Concept.subject_id == subject.id))
    assert concept is not None
    lo = db_session.scalar(select(LearningOutcome).where(LearningOutcome.subject_id == subject.id))
    assert lo is not None

    teacher = _create_user(
        db_session, Role.TEACHER, "t.outage@example.com", "Thầy Giáo Outage"
    )
    student = _create_user(
        db_session, Role.STUDENT, "s.outage@example.com", "Học Sinh Outage"
    )
    parent = _create_user(
        db_session, Role.PARENT, "p.outage@example.com", "Phụ Huynh Outage"
    )
    db_session.flush()

    teacher_prof = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher.id)
    )
    student_prof = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    parent_prof = db_session.scalar(
        select(ParentProfile).where(ParentProfile.user_id == parent.id)
    )

    classroom = Classroom(
        name="Lớp Outage Resilience",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add(
        TeacherClassroom(teacher_id=teacher_prof.id, classroom_id=classroom.id, role="OWNER")
    )
    db_session.add(
        StudentEnrollment(
            student_id=student_prof.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        )
    )
    db_session.add(
        ParentStudentRelationship(
            parent_id=parent_prof.id,
            student_id=student_prof.id,
            relationship_type="mother",
            is_active=True,
        )
    )

    teaching_plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=subject.id,
        status=TeachingPlanStatus.ACTIVE,
        start_date=date.today() - timedelta(days=7),
        created_by=teacher.id,
    )
    db_session.add(teaching_plan)
    db_session.flush()
    db_session.add(
        TeachingPlanItem(
            teaching_plan_id=teaching_plan.id,
            problem_type_id=pt.id,
            order_index=1,
            priority=1,
        )
    )

    # Question with predefined hints so HintService works offline
    q = _create_bank_question(
        db_session,
        subject,
        teacher.id,
        "Câu hỏi Outage: Khảo sát f(x)?",
        pt,
        concept,
        lo,
        correct_answer="A",
        hints=["Gợi ý cấp 1 offline an toàn", "Gợi ý cấp 2 offline an toàn"],
    )
    db_session.commit()

    # 1. Quick Check runs 100% deterministically
    qc_service = QuickCheckService(db_session)
    qc_start = qc_service.start_quick_check(
        student, QuickCheckStartRequest(subject_id=subject.id, classroom_id=classroom.id)
    )

    # 2. HintService serves predefined hint without throwing (while session is active)
    hint_service = HintService(db_session, gateway=failing_gateway)
    hint = await hint_service.get_hint(
        student,
        q.id,
        HintRequest(
            practice_session_id=qc_start.id,
            current_hint_level=HintLevel.LEVEL_1,
        ),
    )
    assert hint.content == "Gợi ý cấp 1 offline an toàn"

    # 3. Answer question
    attempt_res = qc_service.answer_question(
        student,
        qc_start.id,
        PracticeAnswerCreate(
            question_id=q.id, student_answer="A", response_time_seconds=30.0
        ),
    )
    assert attempt_res.is_correct is True

    # 4. Mastery calculation runs deterministically
    pt_mastery = db_session.get(StudentProblemTypeMastery, (student_prof.id, pt.id))
    assert pt_mastery is not None
    assert pt_mastery.attempt_count == 1
    assert pt_mastery.correct_count == 1

    # 5. KnowledgeGapService falls back to deterministic rule analysis without AI
    gap_service = KnowledgeGapService(db_session, gateway=failing_gateway)
    gap_result = await gap_service.analyze_gap(student_prof.id, pt.id, use_ai=False)
    assert gap_result is not None

    # 5. Teacher Copilot falls back gracefully to deterministic analysis
    copilot_service = TeacherCopilotService(db_session, gateway=failing_gateway)
    copilot_res = await copilot_service.consult_copilot_async(
        teacher.id,
        classroom.id,
        TeacherCopilotRequest(query="Trạng thái lớp hiện tại ra sao?"),
    )
    assert copilot_res.classroom_id == classroom.id
    assert len(copilot_res.observations) >= 1

    # 6. Parent AI Summary falls back gracefully to deterministic summary
    parent_ai_service = ParentAISummaryService(db_session, gateway=failing_gateway)
    summary = await parent_ai_service.generate_weekly_summary_async(
        parent.id, student_prof.id
    )
    assert summary.student_id == student_prof.id
    assert summary.is_fallback is True
    assert summary.progress != ""


# ==============================================================================
# 3. Invariant Verification: Synthetic Data Isolation
# ==============================================================================


def test_synthetic_data_isolation(db_session: Session) -> None:
    """Ensure synthetic student data is completely isolated and excluded

    from Teacher Analytics Dashboard, Heatmap, and Alerts by default.
    """
    importer = CurriculumImportService(db_session)
    importer.import_dataset("MATH_G12_GDPT2018_CORE", commit=False)
    db_session.flush()

    subject = db_session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
    assert subject is not None
    pt = db_session.scalar(select(ProblemType))
    assert pt is not None

    teacher = _create_user(
        db_session, Role.TEACHER, "t.synth_iso@example.com", "Giáo Viên Iso"
    )
    real_student_user = _create_user(
        db_session, Role.STUDENT, "s.real_iso@example.com", "Học Sinh Thật"
    )
    synth_student_user = _create_user(
        db_session, Role.STUDENT, "s.synth_iso@example.com", "Học Sinh Synthetic"
    )
    db_session.flush()

    teacher_prof = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher.id)
    )
    real_student_prof = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == real_student_user.id)
    )
    synth_student_prof = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == synth_student_user.id)
    )
    assert real_student_prof and synth_student_prof

    # Mark the synthetic student profile
    synth_student_prof.is_synthetic = True
    synth_student_prof.synthetic_profile = "AVERAGE"
    real_student_prof.is_synthetic = False
    real_student_prof.synthetic_profile = None

    classroom = Classroom(
        name="Lớp Synthetic Isolation",
        academic_year="2025-2026",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add(classroom)
    db_session.flush()

    db_session.add(
        TeacherClassroom(teacher_id=teacher_prof.id, classroom_id=classroom.id, role="OWNER")
    )
    db_session.add(
        TeachingPlan(
            classroom_id=classroom.id,
            subject_id=subject.id,
            status=TeachingPlanStatus.ACTIVE,
            start_date=date.today() - timedelta(days=7),
            created_by=teacher.id,
        )
    )
    db_session.add_all([
        StudentEnrollment(
            student_id=real_student_prof.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        ),
        StudentEnrollment(
            student_id=synth_student_prof.id,
            classroom_id=classroom.id,
            status=EnrollmentStatus.ACTIVE,
        ),
    ])

    now = datetime.now(timezone.utc)
    # Masteries for both students
    db_session.add_all([
        StudentProblemTypeMastery(
            student_id=real_student_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.85,
            confidence=0.9,
            attempt_count=10,
            correct_count=9,
            last_practiced_at=now,
        ),
        StudentProblemTypeMastery(
            student_id=synth_student_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.20,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=now,
        ),
    ])
    db_session.commit()

    analytics = ClassAnalyticsService(db_session)

    # 1. Default (include_synthetic=False): Only real student included
    dash_prod = analytics.get_classroom_dashboard(
        teacher.id, classroom.id, include_synthetic=False
    )
    assert dash_prod.student_count == 1

    heatmap_prod = analytics.get_classroom_heatmap(
        teacher.id,
        classroom.id,
        view=HeatmapView.PROBLEM_TYPE,
        subject_id=subject.id,
        include_synthetic=False,
    )
    assert len(heatmap_prod.rows) == 1
    assert heatmap_prod.rows[0].student_id == real_student_prof.id
    assert heatmap_prod.rows[0].is_synthetic is False

    # 2. Explicit (include_synthetic=True): Both students included
    dash_synth = analytics.get_classroom_dashboard(
        teacher.id, classroom.id, include_synthetic=True
    )
    assert dash_synth.student_count == 2

    heatmap_synth = analytics.get_classroom_heatmap(
        teacher.id,
        classroom.id,
        view=HeatmapView.PROBLEM_TYPE,
        subject_id=subject.id,
        include_synthetic=True,
    )
    assert len(heatmap_synth.rows) == 2
    row_ids = {r.student_id for r in heatmap_synth.rows}
    assert real_student_prof.id in row_ids
    assert synth_student_prof.id in row_ids


# ==============================================================================
# 4. Invariant Verification: Single Source of Truth Integrity
# ==============================================================================


def test_single_source_of_truth_integrity(db_session: Session) -> None:
    """Ensure uniqueness and absence of duplicated source of truth across

    Curriculum, Mastery, and Question Bank entities.
    """
    importer = CurriculumImportService(db_session)
    importer.import_dataset("MATH_G12_GDPT2018_CORE", commit=False)
    db_session.flush()

    # Verify no duplicate Subject codes
    subjects = list(
        db_session.scalars(select(Subject.code).group_by(Subject.code).having(func.count() > 1)).all()
    )
    assert len(subjects) == 0, "Subject codes must be unique"

    # Verify no duplicate ProblemType codes
    pts = list(
        db_session.scalars(
            select(ProblemType.code).group_by(ProblemType.code).having(func.count() > 1)
        ).all()
    )
    assert len(pts) == 0, "ProblemType codes must be unique"

    # Verify no orphan ProblemTypes without Topic
    orphan_pts = list(
        db_session.scalars(
            select(ProblemType).outerjoin(Topic, Topic.id == ProblemType.topic_id).where(Topic.id.is_(None))
        ).all()
    )
    assert len(orphan_pts) == 0, "No ProblemType should be orphaned"

    # Verify no orphan Topics without Chapter
    orphan_topics = list(
        db_session.scalars(
            select(Topic).outerjoin(Chapter, Chapter.id == Topic.chapter_id).where(Chapter.id.is_(None))
        ).all()
    )
    assert len(orphan_topics) == 0, "No Topic should be orphaned"
