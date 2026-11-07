import type { NextRequest } from "next/server";
import { readFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { verifySession } from "@/lib/auth/session-codec";
import { AUTH_COOKIES } from "@/lib/auth/constants";

const MODEL="phxember/Uni-MuMER-Qwen3.5-2B",REVISION="9451fe296d68348d751adc6e71e32be810e6f489";
const PROMPTS={reference:"I have an image of a handwritten mathematical expression. Please write out the expression of the formula in the image using LaTeX format.",strict:"Transcribe exactly the mathematical expression written in the image into LaTeX. Preserve all symbols and any mathematical mistakes as written. Do not solve, simplify, correct, complete, or explain. Output only the LaTeX transcription. If a symbol is unreadable, do not invent missing content."};
let busy=false;
async function gate(request:NextRequest){
  if(process.env.NODE_ENV==="production"||process.env.OCR_V2_EXPERIMENTAL!=="1")return new Response("Not Found",{status:404});
  if(!await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value,process.env.AUTH_SESSION_SECRET??""))return new Response("QA authentication required",{status:401});
  const origin=request.headers.get("origin");if(origin&&origin!==request.nextUrl.origin)return new Response("Same origin required",{status:403});return null;
}
async function server(){
  const directory=path.resolve(process.cwd(),"../.tmp/tri-unimumer-lab");
  const session=JSON.parse(await readFile(path.join(directory,"server-session.json"),"utf8"));
  if(!Number.isInteger(session.port)||session.port<8026||session.port>8035)throw Error("INVALID_FIXED_LOCAL_SERVER_PORT");
  const token=(await readFile(path.join(directory,"server-key.txt"),"utf8")).trim();if(token.length<32)throw Error("MISSING_LOCAL_SERVER_KEY");
  return {directory,base:`http://127.0.0.1:${session.port}`,headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},session};
}
export async function GET(request:NextRequest){
  const denied=await gate(request);if(denied)return denied;
  try{const s=await server(),r=await fetch(s.base+"/health",{headers:s.headers,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(3000)});if(!r.ok)throw Error(`HTTP_${r.status}`);const health=await r.json();
    const p=await fetch(s.base+"/props",{headers:s.headers,cache:"no-store",redirect:"error",signal:AbortSignal.timeout(3000)});const props=await p.json();
    return Response.json({status:health.status==="ok"?"READY":health.status,modelId:MODEL,modelVersion:REVISION,quantization:"Q4_K_M",projector:"Q8_0",profile:s.session.profile,gpuLayers:s.session.verifiedGpuLayers??s.session.layers,projectorDevice:s.session.projectorDevice,runtime:s.session.runtimeVersion,capabilities:props.modalities??"NOT_AVAILABLE"},{headers:{"Cache-Control":"no-store"}});
  }catch(error){return Response.json({status:"UNAVAILABLE",error:`Local Uni-MuMER unavailable: ${String(error)}`},{status:503});}
}
export async function POST(request:NextRequest){
  const denied=await gate(request);if(denied)return denied;
  if(busy)return Response.json({status:"BUSY",error:"One Uni-MuMER request at a time"},{status:429});
  const reader=request.body?.getReader();if(!reader)return new Response("Missing image",{status:400});
  const chunks:Uint8Array[]=[];let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>4_100_000){await reader.cancel();return new Response("Image too large",{status:413});}chunks.push(value);}
  let input:{png:string;sourceStrokeIds:string[];promptId:keyof typeof PROMPTS};
  try{input=JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if(Object.keys(input).some(k=>!["png","sourceStrokeIds","promptId"].includes(k))||typeof input.png!=="string"||!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(input.png)||!Array.isArray(input.sourceStrokeIds)||!input.sourceStrokeIds.length||input.sourceStrokeIds.length>400||input.sourceStrokeIds.some(id=>typeof id!=="string"||!id.trim()||id.length>300)||new Set(input.sourceStrokeIds).size!==input.sourceStrokeIds.length||!Object.hasOwn(PROMPTS,input.promptId))throw Error("INVALID_IMAGE_SCOPE_OR_PROMPT");
  }catch{return new Response("Invalid image/scope/prompt request",{status:400});}
  const raw=Buffer.from(input.png.split(",")[1],"base64"),signature="89504e470d0a1a0a";
  if(raw.length<24||raw.length>3_000_000||raw.subarray(0,8).toString("hex")!==signature||!raw.readUInt32BE(16)||!raw.readUInt32BE(20)||raw.readUInt32BE(16)*raw.readUInt32BE(20)>2_000_000)return new Response("Invalid PNG dimensions/size",{status:400});
  busy=true;const started=performance.now();
  try{const s=await server(),hash=createHash("sha256").update(raw).digest("hex"),body={model:"uni-mumer-qwen3.5-2b-q4_k_m",messages:[{role:"system",content:"You are a helpful assistant."},{role:"user",content:[{type:"image_url",image_url:{url:input.png}},{type:"text",text:PROMPTS[input.promptId]}]}],temperature:0,seed:20261104,max_tokens:384,stream:false,cache_prompt:false,chat_template_kwargs:{enable_thinking:false}};
    const response=await fetch(s.base+"/v1/chat/completions",{method:"POST",headers:s.headers,body:JSON.stringify(body),redirect:"error",signal:AbortSignal.any([request.signal,AbortSignal.timeout(180000)])});
    if(!response.ok)throw Error(`LOCAL_RUNTIME_HTTP_${response.status}`);const result=await response.json(),choice=result.choices?.[0],text=choice?.message?.content;
    if(typeof text!=="string")throw Error("MISSING_RAW_MODEL_OUTPUT");
    const evidence={status:"COMPLETED",modelId:MODEL,modelVersion:REVISION,quantization:"Q4_K_M",projector:"Q8_0",runtime:s.session.runtimeVersion,profile:s.session.profile,rawOutput:text,rawLatex:text,durationMs:performance.now()-started,sourceStrokeIds:input.sourceStrokeIds,inputImageHash:hash,promptId:input.promptId,finishReason:choice.finish_reason,usage:result.usage,timings:result.timings};
    const directory=path.join(s.directory,"lab-evidence");await mkdir(directory,{recursive:true});await writeFile(path.join(directory,hash+".png"),raw,{flag:"wx"}).catch(error=>{if(error.code!=="EEXIST")throw error;});await writeFile(path.join(directory,`${Date.now()}-${hash.slice(0,12)}.json`),JSON.stringify(evidence,null,2));
    return Response.json(evidence,{headers:{"Cache-Control":"no-store"}});
  }catch(error){return Response.json({status:"ERROR",error:String(error),durationMs:performance.now()-started},{status:503});}finally{busy=false;}
}
