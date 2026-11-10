import json,os,sys
from pathlib import Path
from uuid import UUID
R=Path(__file__).parent;os.environ.update(json.loads((R/'environment.json').read_text()));sys.path.insert(0,'D:/SGU/DuAn/Coach_Learning/backend')
from sqlalchemy import select,text,delete
from app.database.session import get_session_factory
from app.curriculum.models import Chapter,Topic,ProblemType
from app.concepts.models import Concept
from app.subjects.models import Subject
from app.questions.models import QuestionConcept
p=json.loads((R/'private.json').read_text(encoding='utf-8'))
maps=[(Chapter,{'DERIVATIVE_APPLICATIONS':'Ứng dụng đạo hàm','EXPONENTIAL_LOGARITHM':'Hàm số mũ và lôgarit','INTEGRALS':'Nguyên hàm và tích phân','PROBABILITY_CHAPTER':'Xác suất','VECTORS_GEOMETRY':'Vectơ và hình học không gian','OXYZ_CHAPTER':'Hình học tọa độ Oxyz'}),(Topic,{'MONOTONICITY_TOPIC':'Tính đơn điệu của hàm số','EXTREMA_TOPIC':'Cực trị của hàm số','FUNCTION_ANALYSIS_TOPIC':'Khảo sát hàm số','EXP_LOG_TOPIC':'Hàm số mũ và lôgarit','INTEGRAL_TOPIC':'Tính tích phân','PROBABILITY_TOPIC':'Mô hình xác suất','VECTOR_TOPIC':'Vectơ và hình học không gian','OXYZ_TOPIC':'Đường thẳng và mặt phẳng trong Oxyz'}),(ProblemType,{'MONOTONICITY_FROM_EXPRESSION':'Đạo hàm và tính đơn điệu','PARAMETER_MONOTONICITY':'Tham số và tính đơn điệu','FIND_FUNCTION_EXTREMA':'Tìm cực trị của hàm số','COMPLETE_FUNCTION_ANALYSIS':'Khảo sát sự biến thiên và đồ thị','EXP_LOG_EQUATION':'Phương trình mũ và lôgarit','CALCULATE_INTEGRAL':'Tính tích phân','BASIC_PROBABILITY':'Xác suất cơ bản','VECTOR_3D_RELATION':'Quan hệ vectơ trong không gian','OXYZ_LINE_PLANE_INTERSECTION':'Giao điểm đường thẳng và mặt phẳng'}),(Concept,{'FUNCTION':'Hàm số','DERIVATIVE':'Đạo hàm','MONOTONICITY':'Tính đơn điệu','EXTREMA':'Cực trị','FUNCTION_ANALYSIS':'Khảo sát hàm số','EXPONENTIAL_FUNCTION':'Hàm số mũ','LOGARITHM':'Lôgarit','INTEGRAL':'Tích phân','PROBABILITY':'Xác suất','VECTOR':'Vectơ','GEOMETRY_3D':'Hình học không gian','OXYZ':'Tọa độ Oxyz','INEQUALITY_SOLVING':'Giải bất phương trình','PARAMETER_REASONING':'Lập luận với tham số'})]
with get_session_factory()() as s:
 if s.execute(text('SELECT current_database()')).scalar()!=p['database']:raise SystemExit('Database mismatch')
 for model,names in maps:
  for row in s.scalars(select(model)):
   if row.code in names:row.name=names[row.code]
 subject=s.get(Subject,UUID(p['subject_id']));subject.name='Toán 12'
 concept=s.scalar(select(Concept).where(Concept.code=='DERIVATIVE'))
 for ident in p['question_ids']:
  s.execute(delete(QuestionConcept).where(QuestionConcept.question_id==UUID(ident)))
  s.add(QuestionConcept(question_id=UUID(ident),concept_id=concept.id,weight=1))
 p['concept_id']=str(concept.id);s.commit()
(R/'private.json').write_text(json.dumps(p,ensure_ascii=False,indent=2),encoding='utf-8')
print('Vietnamese classroom curriculum labels and derivative mappings prepared in isolated database.')
