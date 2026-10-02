from hashlib import sha256
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments.models import AssignmentType, StudentAssignmentMaterialItem
from app.assignments.schemas import AssignmentCreate, AssignmentSubmissionRequest, AnswerSubmitItem
from app.assignments.service import AssignmentService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.learning_evidence.models import LearningEvidenceEvent, LearningEvidenceSourceKind
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.questions.models import QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teacher_materials.ai_schemas import ProposedTaxonomyMapping, TeacherMaterialMappingAIOutput
from app.teacher_materials.extraction import TeacherMaterialExtractor
from app.teacher_materials.mapping_service import TeacherMaterialMappingService
from app.teacher_materials.models import MaterialEvaluationMode, MaterialItemExtractionStatus, MaterialMappingStatus, TeacherMaterialItemConcept, TeacherMaterialItemProblemType, TeacherMaterialStatus
from app.teacher_materials.schemas import MappingCreate, MaterialOptionInput, TeacherMaterialItemUpdate
from app.teacher_materials.service import TeacherMaterialService
from app.teacher_materials.storage import LocalTeacherMaterialStorage
from app.teachers.models import TeacherProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService

PASSWORD="Teacher-Material-Test-Password-2026!"

def setup_domain(session:Session,tmp_path):
    users=UserService(session)
    teacher=users.create_user(UserCreate(email="tm-teacher@example.com",password=PASSWORD,full_name="Teacher",role=Role.TEACHER))
    outsider=users.create_user(UserCreate(email="tm-outsider@example.com",password=PASSWORD,full_name="Outsider",role=Role.TEACHER))
    student=users.create_user(UserCreate(email="tm-student@example.com",password=PASSWORD,full_name="Student",role=Role.STUDENT))
    tp=session.scalar(select(TeacherProfile).where(TeacherProfile.user_id==teacher.id)); sp=session.scalar(select(StudentProfile).where(StudentProfile.user_id==student.id))
    subject=Subject(code="TM-MATH",name="Material Math",grade_level=12); session.add(subject); session.flush()
    chapter=Chapter(subject_id=subject.id,code="TM-CH",name="Functions",order_index=0); session.add(chapter); session.flush()
    topic=Topic(chapter_id=chapter.id,code="TM-TOP",name="Monotonicity",order_index=0); session.add(topic); session.flush()
    pt=ProblemType(topic_id=topic.id,code="TM-MONOTONICITY",name="Parameter monotonicity",order_index=0)
    concept=Concept(subject_id=subject.id,code="TM-INEQUALITY",name="Inequality solving",grade_level=12,order_index=0)
    lo=LearningOutcome(subject_id=subject.id,code="TM-LO",description="Solve monotonicity tasks",grade_level=12,order_index=0)
    classroom=Classroom(name="12A TM",academic_year="2026-2027",grade_level=12,created_by=teacher.id)
    session.add_all([pt,concept,lo,classroom]); session.flush(); session.add_all([TeacherClassroom(teacher_id=tp.id,classroom_id=classroom.id,role="OWNER"),StudentEnrollment(student_id=sp.id,classroom_id=classroom.id,status=EnrollmentStatus.ACTIVE)]); session.commit()
    service=TeacherMaterialService(session,LocalTeacherMaterialStorage(tmp_path/"files"),1024*1024)
    return SimpleNamespace(teacher=teacher,outsider=outsider,student=student,student_profile=sp,subject=subject,classroom=classroom,pt=pt,concept=concept,lo=lo,service=service)

def upload_ready(domain,session):
    material=domain.service.upload(domain.teacher.id,domain.classroom.id,domain.subject.id,"Worksheet","worksheet.txt","text/plain",b"Cau 1. Choose A")
    item=material.items[0]
    domain.service.update_item(domain.teacher.id,item.id,TeacherMaterialItemUpdate(question_type=QuestionType.MULTIPLE_CHOICE,correct_answer="A",difficulty=.5,evaluation_mode=MaterialEvaluationMode.OBJECTIVE_AUTO,content_reviewed=True,options=[MaterialOptionInput(label="A",content="Correct",order_index=0),MaterialOptionInput(label="B",content="Wrong",order_index=1)]))
    domain.service.add_mapping(domain.teacher.id,item.id,"problem-types",MappingCreate(target_id=domain.pt.id,is_primary=True))
    domain.service.add_mapping(domain.teacher.id,item.id,"concepts",MappingCreate(target_id=domain.concept.id))
    domain.service.add_mapping(domain.teacher.id,item.id,"learning-outcomes",MappingCreate(target_id=domain.lo.id))
    domain.service.mark_ready(domain.teacher.id,material.id)
    return domain.service.get(domain.teacher.id,material.id), domain.service._item(domain.teacher.id,item.id)
def test_storage_is_hash_keyed_and_rejects_traversal(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); material=d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"W","safe.txt","text/plain",b"Cau 1")
    assert material.storage_key.endswith(material.sha256+".txt") and "safe" not in material.storage_key
    assert not hasattr(material,"binary")
    with pytest.raises(ValueError): d.service.storage.save("../escape.txt",b"x")
    with pytest.raises(ApplicationError) as exc: d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"X","run.exe","text/plain",b"x")
    assert exc.value.code=="UNSAFE_FILE_NAME"

def test_upload_authorization_size_mime_and_dedupe(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path)
    with pytest.raises(ApplicationError) as exc: d.service.upload(d.outsider.id,d.classroom.id,d.subject.id,"X","x.txt","text/plain",b"x")
    assert exc.value.status_code==403
    with pytest.raises(ApplicationError): d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"X","x.html","text/html",b"x")
    d.service.max_bytes=1
    with pytest.raises(ApplicationError) as exc: d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"X","x.txt","text/plain",b"xx")
    assert exc.value.status_code==413
    d.service.max_bytes=100
    d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"X","x.txt","text/plain",b"same")
    with pytest.raises(ApplicationError) as exc: d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"X2","x2.txt","text/plain",b"same")
    assert exc.value.status_code==409

def test_pdf_extraction_and_empty_pdf_review(monkeypatch):
    class Page:
        def __init__(self,text): self.text=text
        def extract_text(self): return self.text
    monkeypatch.setattr("pypdf.PdfReader",lambda _:SimpleNamespace(pages=[Page("C\u00e2u 1. A"),Page("C\u00e2u 2. B")]))
    result=TeacherMaterialExtractor().extract(b"pdf","application/pdf")
    assert result.page_count==2 and len(result.items)==2
    monkeypatch.setattr("pypdf.PdfReader",lambda _:SimpleNamespace(pages=[Page("")]))
    assert TeacherMaterialExtractor().extract(b"scan","application/pdf").text_empty
def test_ai_overlay_rejects_fake_code_and_stays_suggested(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); material=d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"W","w.txt","text/plain",b"Cau 1. x") ; item=material.items[0]
    mapper=TeacherMaterialMappingService(db_session)
    valid=TeacherMaterialMappingAIOutput(problem_types=[ProposedTaxonomyMapping(code=d.pt.code,weight=1,confidence=.8,is_primary=True)],concepts=[ProposedTaxonomyMapping(code=d.concept.code,weight=1,confidence=.8)])
    mapper.persist_suggestions(item,valid,[d.pt],[d.concept],[d.lo]); db_session.commit()
    assert all(x.status==MaterialMappingStatus.SUGGESTED for x in db_session.scalars(select(TeacherMaterialItemProblemType)).all())
    from app.teacher_materials.schemas import TeacherMaterialItemRead
    refreshed = TeacherMaterialItemRead.model_validate(d.service.get(d.teacher.id, material.id).items[0])
    assert refreshed.problem_type_mappings[0].status == MaterialMappingStatus.SUGGESTED
    assert refreshed.concept_mappings[0].status == MaterialMappingStatus.SUGGESTED
    assert db_session.scalar(select(StudentProblemTypeMastery)) is None
    fake=TeacherMaterialMappingAIOutput(problem_types=[ProposedTaxonomyMapping(code="INVENTED",weight=1,confidence=1)])
    with pytest.raises(ApplicationError): mapper.persist_suggestions(item,fake,[d.pt],[d.concept],[d.lo])

def test_ready_requires_review_and_confirmed_mappings(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); material=d.service.upload(d.teacher.id,d.classroom.id,d.subject.id,"W","w.txt","text/plain",b"Cau 1. x")
    with pytest.raises(ApplicationError): d.service.mark_ready(d.teacher.id,material.id)
    _,item=upload_ready(d,db_session)
    assert item.extraction_status==MaterialItemExtractionStatus.READY and item.material.status==TeacherMaterialStatus.READY

def test_material_assignment_emits_idempotent_evidence_and_mastery(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); _,item=upload_ready(d,db_session)
    assignments=AssignmentService(db_session)
    created=assignments.create_assignment(d.teacher.id,AssignmentCreate(classroom_id=d.classroom.id,subject_id=d.subject.id,title="Material task",assignment_type=AssignmentType.SAME_SET,teacher_material_item_ids=[item.id],question_count=1))
    assignments.publish_assignment(d.teacher.id,created.id)
    read=assignments.get_student_assignment(d.student.id,created.id)
    assert read.questions[0].source_kind=="TEACHER_MATERIAL_ITEM" and read.questions[0].correct_answer is None
    result=assignments.submit_assignment(d.student.id,created.id,AssignmentSubmissionRequest(answers=[AnswerSubmitItem(teacher_material_item_id=item.id,student_answer=" a ",response_time_seconds=12,hint_count=1)]))
    assert result.score==10 and result.results[0].is_correct is True
    event=db_session.scalar(select(LearningEvidenceEvent).where(LearningEvidenceEvent.source_kind==LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM)); assert event is not None and event.response_time_seconds==12 and event.hint_count==1
    cm=db_session.scalar(select(StudentConceptMastery)); pm=db_session.scalar(select(StudentProblemTypeMastery)); assert cm.attempt_count==pm.attempt_count==1
    sm=db_session.scalar(select(StudentAssignmentMaterialItem)); payload_count=db_session.query(LearningEvidenceEvent).count()
    from app.learning_evidence.publisher import LearningEvidencePublisher, LearningEvidencePayload
    from app.mastery.evidence import WeightedConceptEvidence,WeightedProblemTypeEvidence
    LearningEvidencePublisher().publish(LearningEvidencePayload(student_id=d.student_profile.id,subject_id=d.subject.id,source_kind=LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM,source_entity_id=sm.id,is_correct=True,score=1,difficulty=.5,response_time_seconds=12,hint_count=1,evaluation_status=sm.evaluation_status,occurred_at=sm.answered_at,concepts=(WeightedConceptEvidence(d.concept.id,1),),problem_types=(WeightedProblemTypeEvidence(d.pt.id,1,True),)),db_session)
    assert db_session.query(LearningEvidenceEvent).count()==payload_count and cm.attempt_count==pm.attempt_count==1

def test_adaptive_and_cross_scope_material_rejected(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); _,item=upload_ready(d,db_session); service=AssignmentService(db_session)
    with pytest.raises(ApplicationError): service.create_assignment(d.teacher.id,AssignmentCreate(classroom_id=d.classroom.id,subject_id=d.subject.id,title="No",assignment_type=AssignmentType.ADAPTIVE_SET,teacher_material_item_ids=[item.id]))
    other=Subject(code="TM-OTHER",name="Other",grade_level=12); db_session.add(other); db_session.flush()
    other_concept=Concept(subject_id=other.id,code="TM-OTHER-C",name="Other concept",grade_level=12,order_index=0); db_session.add(other_concept); db_session.commit()
    with pytest.raises(ApplicationError) as exc: d.service.add_mapping(d.teacher.id,item.id,"concepts",MappingCreate(target_id=other_concept.id))
    assert exc.value.code=="MAPPING_SUBJECT_MISMATCH"
    with pytest.raises(ApplicationError): service.create_assignment(d.teacher.id,AssignmentCreate(classroom_id=d.classroom.id,subject_id=other.id,title="No",assignment_type=AssignmentType.SAME_SET,teacher_material_item_ids=[item.id]))

def test_evidence_event_is_immutable(db_session:Session,tmp_path):
    d=setup_domain(db_session,tmp_path); _,item=upload_ready(d,db_session); service=AssignmentService(db_session)
    created=service.create_assignment(d.teacher.id,AssignmentCreate(classroom_id=d.classroom.id,subject_id=d.subject.id,title="Immutable",assignment_type=AssignmentType.SAME_SET,teacher_material_item_ids=[item.id],question_count=1)); service.publish_assignment(d.teacher.id,created.id); service.submit_assignment(d.student.id,created.id,AssignmentSubmissionRequest(answers=[AnswerSubmitItem(teacher_material_item_id=item.id,student_answer="A")]))
    event=db_session.scalar(select(LearningEvidenceEvent)); event.hint_count=9
    with pytest.raises(ValueError): db_session.flush()
    db_session.rollback()
