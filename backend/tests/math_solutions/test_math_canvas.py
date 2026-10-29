import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.classes.models import Classroom, StudentEnrollment, TeacherClassroom, EnrollmentStatus
from app.core.exceptions import ApplicationError
from app.math_canvas import router
from app.math_canvas.models import MathCanvasExplanation, MathCanvasSnapshot
from app.math_canvas.schemas import GraphSpec, SnapshotCreate
from app.math_canvas.service import MathCanvasService
from app.math_ink.schemas import InkPageWrite, InkStroke, InkPoint
from app.math_ink.service import MathInkService
from app.math_solutions.models import SolutionAttempt
from app.math_solutions.service import MathSolutionService
from app.mastery.models import StudentConceptMastery
from app.practice.models import PracticeSession, PracticeSessionType, PracticeSessionStatus
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture
def canvas_case(db_session):
    users = UserService(db_session)
    def user(name, role):
        return users.create_user(UserCreate(email=f"canvas-{name}@example.com", password="Canvas-Test-Password-2026!", full_name=name, role=role))
    owner, outsider, teacher, other_teacher = user("owner",Role.STUDENT), user("outsider",Role.STUDENT), user("teacher",Role.TEACHER), user("other",Role.TEACHER)
    student = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == owner.id))
    tp = db_session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == teacher.id))
    classroom = Classroom(name="Canvas class", academic_year="2026-2027", grade_level=12, created_by=teacher.id)
    subject = Subject(code="CANVAS-MATH",name="Canvas Math",grade_level=12)
    db_session.add_all([classroom, subject]); db_session.flush()
    db_session.add_all([TeacherClassroom(teacher_id=tp.id,classroom_id=classroom.id,role="TEACHER"),
        StudentEnrollment(student_id=student.id,classroom_id=classroom.id,status=EnrollmentStatus.ACTIVE)])
    question = Question(subject_id=subject.id, content="Sketch a surface", question_type=QuestionType.OPEN_RESPONSE,
        difficulty=.5, explanation="Explore", source_type="TEST", exam_weight=.5, status=QuestionStatus.APPROVED,created_by=teacher.id)
    db_session.add(question); db_session.flush()
    practice = PracticeSession(student_id=student.id,subject_id=subject.id,session_type=PracticeSessionType.PRACTICE,status=PracticeSessionStatus.ACTIVE)
    db_session.add(practice); db_session.commit()
    attempt = MathSolutionService(db_session).create(owner.id,source_kind="CANONICAL",context_type="SELF_PRACTICE",mode="INDEPENDENT_SOLUTION",
        question_id=question.id,practice_session_id=practice.id,create_idempotency_key="canvas-test-attempt")
    aid = UUID(attempt["id"])
    stroke = InkStroke(id=uuid4(),tool="PEN",color="#123456",width=2,points=[InkPoint(x=.2,y=.3),InkPoint(x=.3,y=.4)])
    MathInkService(db_session).save_page(owner.id, aid, 0, InkPageWrite(expected_document_revision=0,client_action_id=uuid4(),strokes=[stroke]))
    payload = SnapshotCreate(expression="z=x^2+y^2",settings={"parameters":{}},client_action_id=uuid4(),page_index=0,stroke_ids=[stroke.id],
        source_latex="z=x²+y²",camera={"position":[11,12,14],"target":[0,2,0]},note="Curved upward")
    return SimpleNamespace(owner=owner,outsider=outsider,teacher=teacher,other_teacher=other_teacher,student=student, classroom=classroom,aid=aid,payload=payload)


@pytest.mark.parametrize("expression,params,dimension", [("z=x^2+y^2",{},"3D"),("y=sin(x)",{},"2D"),("z=a*x^2+b*y^2",{"a":2,"b":-1},"3D")])
def test_graph_spec_validation(expression,params,dimension):
    from app.math_canvas.schemas import classify_expression
    spec = GraphSpec(expression=expression,settings={"parameters":params})
    assert classify_expression(spec.expression)[0] == dimension


@pytest.mark.parametrize("expression", ["z=__import__('os')", "z=x.real", "z=[x]", "y=y+x", "z=z+x", "z=sin+x", "z=x//2", "z=1e309"])
def test_reject_unsafe_and_unsupported_formulas(expression):
    with pytest.raises(ValidationError): GraphSpec(expression=expression,settings={"parameters":{}})


def test_snapshot_replay_immutable_ink_and_no_learning_mutation(db_session,canvas_case):
    case = canvas_case; service = MathCanvasService(db_session)
    result = service.save(case.owner.id,case.aid,case.payload)
    assert result.dimension == "3D" and result.source_strokes[0]["id"] == str(case.payload.stroke_ids[0])
    assert service.save(case.owner.id,case.aid,case.payload).id == result.id
    assert db_session.scalar(select(func.count()).select_from(MathCanvasSnapshot)) == 1
    assert db_session.scalar(select(func.count()).select_from(StudentConceptMastery)) == 0
    assert db_session.get(SolutionAttempt,case.aid).status == "DRAFT"
    assert len(service.list_student(case.owner.id,case.aid)) == 1
    with pytest.raises(ApplicationError) as err:
        service.save(case.owner.id,case.aid,case.payload.model_copy(update={"note":"Changed"}))
    assert err.value.code == "CANVAS_ACTION_REUSED"
    MathInkService(db_session).save_page(case.owner.id,case.aid,0,InkPageWrite(expected_document_revision=1,client_action_id=uuid4(),strokes=[]))
    assert len(service.list_student(case.owner.id,case.aid)[0].source_strokes) == 1
    with pytest.raises(ApplicationError) as err:
        service.save(case.owner.id,case.aid,case.payload.model_copy(update={"client_action_id":uuid4()}))
    assert err.value.code == "CANVAS_SELECTION_STALE"


def test_student_isolation_and_teacher_enrollment_revocation(db_session,canvas_case):
    case=canvas_case; service=MathCanvasService(db_session)
    service.save(case.owner.id,case.aid,case.payload)
    with pytest.raises(ApplicationError) as err: service.list_student(case.outsider.id,case.aid)
    assert err.value.status_code == 404
    with pytest.raises(ApplicationError): service.save(case.outsider.id,case.aid,case.payload)
    assert len(service.list_teacher(case.teacher.id)) == 1
    assert service.list_teacher(case.other_teacher.id) == []
    enrollment=db_session.get(StudentEnrollment,(case.student.id,case.classroom.id)); enrollment.status=EnrollmentStatus.INACTIVE; db_session.commit()
    assert service.list_teacher(case.teacher.id) == []


def test_explanation_is_server_generated_and_bound_to_parameters(db_session,canvas_case,settings,monkeypatch):
    case=canvas_case; calls=[]
    class Gateway:
        async def generate(self,*args,**kwargs):
            calls.append(args); return SimpleNamespace(content="Bề mặt mở lên; tăng s làm tăng độ cao.",model="test-model")
    class Limiter:
        def check_rate_limit(self,*args,**kwargs): pass
    monkeypatch.setattr(router,"get_ai_gateway_singleton",lambda config:Gateway())
    configured=settings.model_copy(update={"ai_provider":"gemini"})
    spec=GraphSpec(expression=case.payload.expression,settings=case.payload.settings)
    explanation=asyncio.run(router.explain(case.aid,spec,case.owner,db_session,configured,Limiter()))
    assert len(calls)==1 and explanation.provider=="gemini"
    service=MathCanvasService(db_session)
    good=case.payload.model_copy(update={"explanation_id":explanation.id})
    saved=service.save(case.owner.id,case.aid,good)
    assert saved.explanation.text==explanation.text
    bad=good.model_copy(update={"client_action_id":uuid4(),"settings":good.settings.model_copy(update={"scale":2})})
    with pytest.raises(ApplicationError) as err: service.save(case.owner.id,case.aid,bad)
    assert err.value.code=="CANVAS_EXPLANATION_STALE"
    with pytest.raises(ApplicationError) as err:
        asyncio.run(router.explain(case.aid,spec,case.owner,db_session,settings,Limiter()))
    assert err.value.code=="CANVAS_AI_UNAVAILABLE"
    assert db_session.scalar(select(func.count()).select_from(MathCanvasExplanation))==1


def test_api_auth_and_migration_tables(db_client,db_session):
    assert db_client.get("/api/v3/math-canvas/teacher/snapshots").status_code==401
    assert db_client.get(f"/api/v3/math-canvas/attempts/{uuid4()}/snapshots").status_code==401
    assert db_session.scalar(select(func.count()).select_from(MathCanvasSnapshot))==0


@pytest.mark.parametrize("expression,mode", [("y=1-x^2","2D"),("y=1-x^2","3D"),("y=1-x^2","EXTRUDED"),("z=x^2+y^2","2D"),("z=x^2+y^2","3D")])
def test_presentation_is_independent_of_function_classification(expression,mode):
    spec=GraphSpec(expression=expression,settings={"parameters":{},"view_mode":mode,"slice_y":1})
    assert spec.expression==expression
    assert spec.settings.view_mode==mode


def test_presentation_rejects_invalid_surface_extension_and_out_of_range_slice():
    with pytest.raises(ValidationError):
        GraphSpec(expression="z=x^2+y^2",settings={"parameters":{},"view_mode":"EXTRUDED"})
    with pytest.raises(ValidationError):
        GraphSpec(expression="z=x^2+y^2",settings={"parameters":{},"view_mode":"2D","slice_y":float("nan")})
    with pytest.raises(ValidationError):
        GraphSpec(expression="z=x^2+y^2",settings={"parameters":{},"view_mode":"2D","slice_y":10})


def test_save_and_teacher_review_restore_spatial_curve_without_rewriting_formula(db_session,canvas_case):
    case=canvas_case; service=MathCanvasService(db_session)
    data=case.payload.model_copy(update={"expression":"y=1-x^2","source_latex":"y=1-x²",
        "settings":case.payload.settings.model_copy(update={"view_mode":"3D"})})
    saved=service.save(case.owner.id,case.aid,data)
    assert saved.dimension=="2D"
    assert saved.settings.view_mode=="3D"
    assert saved.expression=="y=1-x^2"
    restored=service.list_teacher(case.teacher.id)[0]
    assert restored.settings.view_mode=="3D" and restored.camera==data.camera


def test_legacy_graph_hash_remains_compatible_with_default_presentation():
    from app.math_canvas.service import fingerprint,spec_hash
    spec=GraphSpec(expression="z=x^2+y^2",settings={"parameters":{}})
    legacy=spec.settings.model_dump(mode="json",exclude={"view_mode","slice_y","scene"})
    assert spec_hash(spec)==fingerprint({"expression":spec.expression,"settings":legacy})
    changed=spec.model_copy(update={"settings":spec.settings.model_copy(update={"view_mode":"2D","slice_y":1})})
    assert spec_hash(changed)!=spec_hash(spec)


@pytest.mark.parametrize("expression,params,dimension", [
    ("x^2+y^2+z^2=r^2", {"r": 2}, "3D"), ("x+2*y+3*z=a", {"a": 1}, "3D"),
    ("x^2+y^2=4", {}, "2D"), ("x=2", {}, "2D"), ("sin(x)-(x)=2*y", {}, "2D"),
])
def test_implicit_equation_validation(expression, params, dimension):
    from app.math_canvas.schemas import classify_expression
    spec = GraphSpec(expression=expression, settings={"parameters": params})
    assert classify_expression(spec.expression) == (dimension, set(params))


@pytest.mark.parametrize("expression", ["x=x.__class__", "x=sin", "x^2+y^2=eval(x)", "2=3", "x=y=1"])
def test_implicit_equations_still_reject_unsafe_or_unsupported_syntax(expression):
    with pytest.raises(ValidationError):
        GraphSpec(expression=expression, settings={"parameters": {}})


def test_implicit_snapshot_restores_equation_parameters_slice_and_orthographic_zoom(db_session, canvas_case):
    case = canvas_case
    data = SnapshotCreate(**{**case.payload.model_dump(), "expression": "x^2+y^2+z^2=r^2",
        "settings": {"parameters": {"r": 2}, "view_mode": "2D", "slice_y": 1},
        "camera": {"position": [0,0,16], "target": [0,0,0], "zoom": 1.5}})
    service = MathCanvasService(db_session)
    saved = service.save(case.owner.id, case.aid, data)
    restored = service.list_teacher(case.teacher.id)[0]
    assert restored.expression == data.expression and saved.dimension == "3D"
    assert restored.settings.parameters == {"r": 2}
    assert restored.settings.view_mode == "2D" and restored.settings.slice_y == 1
    assert restored.camera.zoom == 1.5


def test_implicit_equations_reject_function_transforms_and_extrusion():
    for settings in [{"scale": 2}, {"shift_x": 1}, {"view_mode": "EXTRUDED"}]:
        with pytest.raises(ValidationError):
            GraphSpec(expression="x^2+y^2=4", settings={"parameters": {}, **settings})


def graph_scene(expressions, combine="AND"):
    return {"version": 2, "dimension": "2D", "combine": combine, "rows": [
        {"id": f"row-{index}", "expression": expression, "visible": True, "color": "#2563eb"}
        for index, expression in enumerate(expressions)]}


@pytest.mark.parametrize("expressions,parameters", [
    (["y>=x^2", "y<=1"], {}), (["0<=x<=2", "y=sin(x)"], {}),
    (["y=f(g(x))", "f(x)=a*x^2+1", "g(x)=sin(x)"], {"a": 2}),
    (["f(x)=1", "y=f(1/x)"], {}), (["x^2+y^2<=r^2", "x>=0"], {"r": 2}),
])
def test_versioned_scene_validation(expressions, parameters):
    spec = GraphSpec(expression="y=0", settings={"parameters": parameters, "scene": graph_scene(expressions)})
    assert spec.settings.scene.version == 2


@pytest.mark.parametrize("expressions", [
    ["y=__import__(x)"], ["y=x.real"], ["y=x//2"], ["y=>x"], ["x=y=1"], ["y=f(x)"],
    ["f(x)=g(x)", "g(x)=f(x)"], ["f(x)=x", "f(x)=x^2"], ["z=x^2+y^2"], ["f(x)=y"],
    ["f(x)=x+x+x+x", "g(x)=f(f(f(f(f(x)))))"],
])
def test_scenes_reject_unsafe_ambiguous_or_unbounded_inputs(expressions):
    with pytest.raises(ValidationError):
        GraphSpec(expression="y=0", settings={"parameters": {}, "scene": graph_scene(expressions)})


def test_scene_shared_parameters_and_legacy_transforms_are_not_silently_accepted():
    for settings in [{"parameters": {}}, {"parameters": {"a": 2}, "scale": 2}, {"parameters": {"a": 2}, "view_mode": "3D"}]:
        with pytest.raises(ValidationError):
            GraphSpec(expression="y=0", settings={**settings, "scene": graph_scene(["y>=a*x^2"])})


def test_scene_snapshot_replay_and_teacher_restore_all_rows(db_session, canvas_case):
    case = canvas_case
    payload = SnapshotCreate(**{**case.payload.model_dump(), "expression": "y=0", "settings": {
        "parameters": {"a": 2}, "scene": graph_scene(["f(x)=a*x^2", "y>=f(x)", "y<=3"]), "view_mode": "2D"}})
    service = MathCanvasService(db_session)
    saved = service.save(case.owner.id, case.aid, payload)
    assert service.save(case.owner.id, case.aid, payload).id == saved.id
    restored = service.list_teacher(case.teacher.id)[0]
    assert restored.settings.scene.model_dump() == payload.settings.scene.model_dump()
    assert restored.settings.parameters == {"a": 2}
    with pytest.raises(ApplicationError):
        service.list_student(case.outsider.id, case.aid)
