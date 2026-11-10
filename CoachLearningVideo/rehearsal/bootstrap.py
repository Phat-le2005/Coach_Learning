"""Create an isolated video database; never rename records in the working database."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import unicodedata
from uuid import uuid5, NAMESPACE_URL

REPO=Path('D:/SGU/DuAn/Coach_Learning'); ROOT=Path(__file__).parent
sys.path.insert(0,str(REPO/'backend'))
from sqlalchemy import create_engine,select,text
from app.core.config import get_settings

PRIVATE=ROOT/'private.json'; DB='coach_video_qa_20261109'
base=get_settings()
if base.app_env=='production':raise SystemExit('Refusing production configuration')
if not PRIVATE.exists():
 PRIVATE.write_text(json.dumps({'database':DB,'password':secrets.token_urlsafe(20),'jwt_secret':secrets.token_urlsafe(48),'session_secret':secrets.token_urlsafe(48)},indent=2),encoding='utf-8')
private=json.loads(PRIVATE.read_text())
if private['database']!=DB:raise SystemExit('Database identity mismatch')
admin=create_engine(base.database_url.set(database='postgres',host='127.0.0.1'),isolation_level='AUTOCOMMIT',hide_parameters=True,connect_args={'connect_timeout':5})
with admin.connect() as c:
 if not c.execute(text('SELECT 1 FROM pg_database WHERE datname=:name'),{'name':DB}).scalar():
  c.exec_driver_sql('CREATE DATABASE '+DB)
admin.dispose()
env=os.environ.copy();env.update({'DATABASE_HOST':'127.0.0.1','DATABASE_NAME':DB,'APP_ENV':'development','SEED_DEMO_PASSWORD':private['password'],'JWT_SECRET_KEY':private['jwt_secret'],'FRONTEND_URL':'http://127.0.0.1:3150','TEACHER_MATERIAL_STORAGE_DIR':str(ROOT/'storage/materials'),'TEACHER_PDF_IMPORT_DIR':str(ROOT/'storage/pdf-imports'),'MATH_PAPER_STORAGE_DIR':str(ROOT/'storage/paper')})
(ROOT/'environment.json').write_text(json.dumps({k:v for k,v in env.items() if k in ['DATABASE_HOST','DATABASE_NAME','APP_ENV','JWT_SECRET_KEY','FRONTEND_URL','TEACHER_MATERIAL_STORAGE_DIR','TEACHER_PDF_IMPORT_DIR','MATH_PAPER_STORAGE_DIR']},indent=2),encoding='utf-8')
for label,args in [('migrations',['-m','alembic','upgrade','head']),('seed',['-m','app.seed'])]:
 with (ROOT/(label+'.log')).open('wb') as log:
  result=subprocess.run([sys.executable,*args],cwd=REPO/'backend',env=env,stdout=log,stderr=log)
 if result.returncode:raise SystemExit(label+' failed; inspect private rehearsal log')
os.environ.update(env);get_settings.cache_clear()
from app.database.session import get_session_factory
from app.users.models import User,Role
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.classes.models import Classroom,StudentEnrollment
from app.curriculum.models import ProblemType,Topic,Chapter
from app.concepts.models import Concept
from app.questions.models import Question,QuestionStatus,QuestionType,QuestionConcept,QuestionProblemType
from app.seed_step_review_demo import install
from data.seed.demo_users import STUDENTS,TEACHERS,PARENTS,ADMIN
from data.seed.identifiers import stable_id

names=[('Nguyễn Minh Anh','minhanh'),('Trần Gia Huy','giahuy'),('Lê Ngọc Hân','ngochan'),('Phạm Tuấn Kiệt','tuankiet'),('Võ Khánh Linh','khanhlinh'),('Đặng Hoàng Nam','hoangnam'),('Huỳnh Bảo Ngọc','baongoc'),('Bùi Quang Minh','quangminh'),('Đỗ Phương Thảo','phuongthao'),('Nguyễn Đức Anh','ducanh'),('Trần Mai Chi','maichi'),('Lê Nhật Minh','nhatminh')]
accounts=[]
with get_session_factory()() as session:
 if session.execute(text('SELECT current_database()')).scalar()!=DB:raise SystemExit('Unsafe database')
 groups=[(STUDENTS,names),(TEACHERS,[('Nguyễn Thu Hà','thuha'),('Trần Minh Quân','minhquan')]),(PARENTS,[('Nguyễn Thanh Tâm','thanhtam'),('Trần Hoài Phương','hoaiphuong'),('Lê Thị Hồng','thihong'),('Phạm Quốc Bảo','quocbao')]),([ADMIN],[('Nguyễn Hải Đăng','haidang')])]
 for records,labels in groups:
  for record,(name,slug) in zip(records,labels):
   user=session.get(User,stable_id('user',record.code));user.full_name=name;user.email=slug+'@demo.com'
   accounts.append({'id':str(user.id),'role':user.role.value,'name':name,'email':user.email})
 classes=list(session.scalars(select(Classroom).order_by(Classroom.name)))
 for index,cl in enumerate(classes):cl.name=['12A1','12A2'][index] if index<2 else f'12A{index+1}'
 session.commit()
 subject=session.scalar(select(Subject).where(Subject.code=='MATH_G12'))
 pts=list(session.scalars(select(ProblemType).join(Topic).join(Chapter).where(Chapter.subject_id==subject.id)))
 pt=next((p for p in pts if 'đạo hàm' in p.name.lower()),pts[0])
 concepts=list(session.scalars(select(Concept).where(Concept.subject_id==subject.id)))
 concept=next((p for p in concepts if 'đạo hàm' in p.name.lower()),concepts[0])
 teacher=next(x for x in accounts if x['role']=='TEACHER')
 from uuid import UUID
 questions=[]
 samples=[('Tính đạo hàm của hàm số $y=x^3-3x$.',r"y'=3x^2-3",'Đạo hàm của x³ là 3x²; đạo hàm của -3x là -3.'),('Tính đạo hàm của hàm số $y=x^2-2x$.',r"y'=2x-2",'Áp dụng đạo hàm tổng và đạo hàm hàm lũy thừa.'),('Tìm các điểm có đạo hàm bằng 0 của $y=x^3-3x$.',r'x=-1; x=1',"Ta có y'=3x²-3. Giải y'=0 được x=±1.")]
 for i,(content,answer,explanation) in enumerate(samples):
  ident=uuid5(NAMESPACE_URL,f'coach-video-question-{i}')
  q=session.get(Question,ident)
  if q is None:
   q=Question(id=ident,subject_id=subject.id,content=content,question_type=QuestionType.OPEN_RESPONSE,difficulty=.35+i*.1,correct_answer=answer,explanation=explanation,source_type='VIDEO_REHEARSAL',source_reference='Bài tập soạn riêng cho lớp 12A1',exam_weight=.5,status=QuestionStatus.APPROVED,created_by=UUID(teacher['id']))
   session.add(q);session.flush();session.add_all([QuestionConcept(question_id=q.id,concept_id=concept.id,weight=1),QuestionProblemType(question_id=q.id,problem_type_id=pt.id,weight=1,is_primary=True)])
  questions.append(str(ident))
 session.commit()
 student=next(x for x in accounts if x['role']=='STUDENT')
 profile=session.scalar(select(StudentProfile).where(StudentProfile.user_id==UUID(student['id'])))
 enrollment=session.scalar(select(StudentEnrollment).where(StudentEnrollment.student_id==profile.id))
 private.update({'accounts':accounts,'student':student,'teacher':teacher,'student_profile_id':str(profile.id),'classroom_id':str(enrollment.classroom_id),'subject_id':str(subject.id),'problem_type_id':str(pt.id),'concept_id':str(concept.id),'question_ids':questions})
 PRIVATE.write_text(json.dumps(private,ensure_ascii=False,indent=2),encoding='utf-8')
install()
print('Created isolated rehearsal database, Vietnamese identities and reference questions; credentials omitted.')
