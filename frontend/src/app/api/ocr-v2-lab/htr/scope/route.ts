import type { NextRequest } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { verifySession } from "@/lib/auth/session-codec";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { planAutomaticRouting } from "@/features/math-workspace/utils/ocr-automatic-routing";
import { sourceKey, validateLabSource } from "@/features/math-workspace/utils/ocr-v2-experimental";

let busy=false;
export async function POST(request:NextRequest){
  if(process.env.NODE_ENV==='production'||process.env.OCR_V2_EXPERIMENTAL!=='1')return new Response('Not Found',{status:404});
  if(!await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value,process.env.AUTH_SESSION_SECRET??''))return new Response('QA authentication required',{status:401});
  const origin=request.headers.get('origin');if(origin&&origin!==request.nextUrl.origin)return new Response('Same origin required',{status:403});
  if(busy)return Response.json({error:'HTR_BUSY'},{status:429});
  const reader=request.body?.getReader();if(!reader)return new Response('Missing scope',{status:400});
  const chunks:Uint8Array[]=[];let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>4_000_000){await reader.cancel();return new Response('Scope too large',{status:413});}chunks.push(value);}
  let payload;
  try{
    const input=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if(Object.keys(input).sort().join(',')!=='perception,png,scope,source')throw Error('SOURCE_SCOPE_IMAGE_ONLY');
    validateLabSource(input.source);
    const route=planAutomaticRouting(input.source,[input.scope],input.perception)[0];
    if(route?.action!=='VIETOCR')return Response.json({error:'TEXT_EVIDENCE_INSUFFICIENT',reasons:route?.reasons},{status:422});
    if(typeof input.png!=='string'||!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(input.png))throw Error('PNG_REQUIRED');
    const bytes=Buffer.from(input.png.split(',')[1],'base64');
    if(bytes.length<24||bytes.length>2_000_000||bytes.subarray(0,8).toString('hex')!=='89504e470d0a1a0a'||!bytes.readUInt32BE(16)||!bytes.readUInt32BE(20)||bytes.readUInt32BE(16)*bytes.readUInt32BE(20)>2_000_000)throw Error('INVALID_PNG');
    payload={png:input.png,scopeId:input.scope.id,sourceStrokeIds:route.sourceStrokeIds,sourceSnapshotSha256:createHash('sha256').update(sourceKey(input.source)).digest('hex'),sourceRevision:input.source.sourceRevision,pageIndex:input.source.pageIndex,originalKind:input.scope.kind};
  }catch(e){return Response.json({error:String(e)},{status:400});}
  busy=true;
  try{
    const token=(await readFile(path.resolve(process.cwd(),'../.tmp/tri-vietnamese-htr/server-key.txt'),'utf8')).trim();
    if(token.length<32)throw Error('HTR_SERVICE_NOT_STARTED');
    const response=await fetch('http://127.0.0.1:8041/infer-scope',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:JSON.stringify(payload),redirect:'error',signal:AbortSignal.any([request.signal,AbortSignal.timeout(120000)])});
    const value=await response.json();if(!response.ok)throw Error(value.detail??`LOCAL_HTR_${response.status}`);
    return Response.json(value,{headers:{'Cache-Control':'no-store'}});
  }catch(e){return Response.json({status:'ERROR',error:String(e)},{status:503});}finally{busy=false;}
}
