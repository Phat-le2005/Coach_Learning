import { editDistance } from "./ocr-evaluation-metrics";
/** Presentation parsing only; raw evidence is never changed. No algebra/CAS. */
export function unwrapMathOutput(raw: string): string {
  let text=raw.trim();
  const fence=text.match(/^```(?:latex|tex)?\s*\n?([\s\S]*?)\n?```$/i);if(fence)text=fence[1].trim();
  if((text.startsWith("\\[")&&text.endsWith("\\]"))||(text.startsWith("\\(")&&text.endsWith("\\)")))text=text.slice(2,-2).trim();
  else if(text.startsWith("$$")&&text.endsWith("$$"))text=text.slice(2,-2).trim();
  else if(text.startsWith("$")&&text.endsWith("$")&&text.length>=2)text=text.slice(1,-1).trim();
  return text;
}
export const mathTokens=(s:string)=>s.normalize("NFC").match(/\\[a-zA-Z]+|\\.|[^\s]/g)??[];
export function normalizedMathTokens(raw:string):string[] {
  const tokens=mathTokens(unwrapMathOutput(raw));
  // Declared presentation-only conventions. No symbol synonyms or implied operations.
  const filtered=tokens.filter(t=>!["\\left","\\right","\\limits","\\nolimits","\\displaystyle","\\textstyle","\\,","\\;","\\!","\\quad","\\qquad"].includes(t));
  function consume(index:number):{value:string[];next:number}{
    if(index>=filtered.length)return {value:[],next:index};
    const token=filtered[index];
    if(token==="{"){const result=[token];let depth=1,j=index+1;for(;j<filtered.length;j++){result.push(filtered[j]);if(filtered[j]==="{")depth++;if(filtered[j]==="}"&&!--depth){j++;break;}}return {value:result,next:j};}
    return {value:[token],next:index+1};
  }
  const result:string[]=[];
  for(let i=0;i<filtered.length;){const token=filtered[i++];result.push(token);
    if(token==="\\frac")for(let n=0;n<2;n++){const atom=consume(i);if(!atom.value.length)break;result.push(...(atom.value[0]==="{"?atom.value:["{",...atom.value,"}"]));i=atom.next;}
  }
  return result;
}
/** Unit-cost Levenshtein alignment, deterministic tie-break diagonal, deletion, insertion. */
export function tokenAlignment(prediction:string[],reference:string[]) {
  const rows=reference.length+1,cols=prediction.length+1;
  const d=Array.from({length:rows},(_,i)=>Array.from({length:cols},(_,j)=>i?j?0:i:j));
  for(let i=1;i<rows;i++)for(let j=1;j<cols;j++)d[i][j]=Math.min(d[i-1][j-1]+Number(reference[i-1]!==prediction[j-1]),d[i-1][j]+1,d[i][j-1]+1);
  let i=reference.length,j=prediction.length,missing=0,extra=0,substitutions=0;
  while(i||j){if(i&&j&&d[i][j]===d[i-1][j-1]+Number(reference[i-1]!==prediction[j-1])){substitutions+=Number(reference[i-1]!==prediction[j-1]);i--;j--;}else if(i&&d[i][j]===d[i-1][j]+1){missing++;i--;}else{extra++;j--;}}
  return {distance:d[reference.length][prediction.length],missingTokens:missing,extraTokens:extra,substitutions,referenceTokens:reference.length};
}
export function compareMathRecognizers(prediction:string,reference:string) {
  const p=normalizedMathTokens(prediction),r=normalizedMathTokens(reference),aligned=tokenAlignment(p,r);
  const chars=[...unwrapMathOutput(reference).normalize("NFC").replace(/\s/g,"")];
  const predictedChars=[...unwrapMathOutput(prediction).normalize("NFC").replace(/\s/g,"")];
  return {strictExact:prediction.trim()===reference.trim(),lexicalExact:JSON.stringify(mathTokens(unwrapMathOutput(prediction)))===JSON.stringify(mathTokens(unwrapMathOutput(reference))),normalizedExact:JSON.stringify(p)===JSON.stringify(r),tokenErrorRate:r.length?aligned.distance/r.length:null,characterErrorRate:chars.length?editDistance(predictedChars,chars)/chars.length:null,missingSymbolRate:r.length?aligned.missingTokens/r.length:null,extraSymbolRate:r.length?aligned.extraTokens/r.length:null,...aligned,
    normalization:"NFC, strip outer math/markdown wrappers, lexical whitespace, declared presentation commands and brace single-atom frac arguments. No algebra, CAS, symbol substitution or GT-guided repair. Missing/extra are token-alignment proxies, not glyph-level CDM."};
}
