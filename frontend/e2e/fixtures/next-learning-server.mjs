// Isolated UI fixture: no model, no credentials, no database and no external I/O.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
const base = JSON.parse(readFileSync(new URL("./gemini-review.json", import.meta.url), "utf8"));
const plan = JSON.parse(readFileSync(new URL("./next-learning.json", import.meta.url), "utf8"));
const steps = [
  {id:"00000000-0000-4000-8000-000000000301",step_index:1,step_type:"DERIVATIVE_CALCULATION",content_latex:"y'=3x^2-3",explanation_text:null,step_revision_number:1},
  {id:"00000000-0000-4000-8000-000000000302",step_index:2,step_type:"ROOT_FINDING",content_latex:"x=-1 \\lor x=1",explanation_text:null,step_revision_number:1},
];
const attempt = {...base.attempt, status:"EVALUATED", steps};
const review = {attempt_id:attempt.id,is_final:true,review_source:"ANSWER_GROUNDED_AI",final_score:.5,needs_teacher_review:false,
  step_grades:steps.map(step=>({step_index:step.step_index,verdict:"VALID",score:1,confidence:.95,feedback:"Bước biến đổi này hợp lý; bài vẫn cần đủ các tiêu chí rubric."}))};
createServer((request, response) => {
  const url = new URL(request.url, "http://127.0.0.1:8898");
  const path = url.pathname;
  const body = path === "/health" ? {status:"ok"}
    : path.endsWith('/next-learning/explain') ? {text:'Ôn cách liên hệ dấu đạo hàm với chiều biến thiên, rồi tự đối chiếu kết luận sau khi lập bảng. Hoàn thành bài củng cố để kiểm tra lại.',source:'AI_COACH'}
    : path.endsWith("/next-learning") ? request.method === "POST" ? {attempt_id:"00000000-0000-4000-8000-000000000204"} : plan
    : path.endsWith("/ai-review") ? request.method === "GET" ? {available:true, reason_code:null, cached_review:review} : review
    : path.endsWith("/problem") ? {...base.problem, is_read_only:true}
    : path.endsWith("/ink") ? base.document : path.endsWith("/ink/pages/0") ? base.page : attempt;
  response.writeHead(200, {"Content-Type":"application/json"}); response.end(JSON.stringify(body));
}).listen(8898, "127.0.0.1");
