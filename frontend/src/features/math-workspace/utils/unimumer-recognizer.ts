import { unwrapMathOutput } from "./math-recognizer-comparison";

export type MathRecognizer = "COMER" | "UNIMUMER" | "COMPARE";
export interface UniMumerEvidence {
  modelId: "phxember/Uni-MuMER-Qwen3.5-2B"; modelVersion: string; quantization: "Q4_K_M";
  runtime: string; profile: string; projector: "Q8_0"; status: "COMPLETED" | "ERROR";
  rawOutput: string; rawLatex: string; normalizedLatex: string; durationMs: number;
  sourceStrokeIds: string[]; inputImageHash: string; promptId: "reference" | "strict";
  finishReason?: string; usage?: unknown; timings?: unknown; error?: string;
}
export interface UniMumerHealth { status: string; modelId?: string; profile?: string; gpuLayers?: number; projectorDevice?: string; error?: string; capabilities?: unknown }
export async function uniMumerHealth(): Promise<UniMumerHealth> {
  try { const r=await fetch("/api/ocr-v2-lab/unimumer",{cache:"no-store",signal:AbortSignal.timeout(5000)});return await r.json(); }
  catch(error){return {status:"UNAVAILABLE",error:String(error)};}
}
/** Receives only the selected image and ink identity, never a reference transcript. */
export async function recognizeUniMumer(png:string,sourceStrokeIds:string[],promptId:"reference"|"strict"="reference",signal?:AbortSignal):Promise<UniMumerEvidence>{
  if(process.env.NODE_ENV==="production")throw Error("QA_RECOGNIZER_DISABLED_IN_PRODUCTION");
  if(!sourceStrokeIds.length||new Set(sourceStrokeIds).size!==sourceStrokeIds.length)throw Error("INVALID_SOURCE_STROKE_IDS");
  const response=await fetch("/api/ocr-v2-lab/unimumer",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({png,sourceStrokeIds,promptId}),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(180000)]):AbortSignal.timeout(180000)});
  const body=await response.json();
  if(!response.ok||body.status!=="COMPLETED")throw Error(body.error??body.status??`UNIMUMER_HTTP_${response.status}`);
  if(JSON.stringify(body.sourceStrokeIds)!==JSON.stringify(sourceStrokeIds))throw Error("RECOGNIZER_SOURCE_IDENTITY_MISMATCH");
  return {...body,normalizedLatex:unwrapMathOutput(body.rawOutput)};
}
