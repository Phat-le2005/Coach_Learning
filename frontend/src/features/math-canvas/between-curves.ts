import { evaluateMath } from "./expression";
import type { CompiledScene } from "./scene";
import type { SceneFill } from "./scene-geometry";
import { explicitSceneCurve } from "./scene-curve";
type Point=[number,number];
function clipY(polygon:Point[],cut:number,above:boolean):Point[]{
  const output:Point[]=[];
  for(let i=0;i<polygon.length;i++){
    const a=polygon[i],b=polygon[(i+1)%polygon.length],inside=above?a[1]>=cut:a[1]<=cut,nextInside=above?b[1]>=cut:b[1]<=cut;
    if(inside)output.push(a);
    if(inside!==nextInside){const t=(cut-a[1])/(b[1]-a[1]);output.push([a[0]+t*(b[0]-a[0]),cut]);}
  }
  return output;
}

/** Shade bounded lobes between exactly two visible y=f(x) curves. Keep the
 * original relations untouched; undefined/pole intervals never become solids.
 * null means unsupported; [] means supported but no closed lobe was found.
 */
export function sampleBetweenCurves(scene:CompiledScene,parameters:Record<string,number>,domain:number,intersections:Point[]):SceneFill[]|null{
  const layers=scene.layers.filter((layer)=>layer.visible);
  if(layers.length!==2)return null;
  const nodes=layers.map(explicitSceneCurve);
  if(!nodes[0]||!nodes[1])return null;
  const values={...parameters,x:0};
  const pair=(x:number):Point=>{values.x=x;return [evaluateMath(nodes[0]!,values),evaluateMath(nodes[1]!,values)];};
  const difference=(x:number)=>{const [a,b]=pair(x);return a-b;};
  const refine=(hint:number):number|null=>{
    let a=Math.max(-domain,hint-domain/28),b=Math.min(domain,hint+domain/28),va=difference(a),vb=difference(b);
    if(!Number.isFinite(va)||!Number.isFinite(vb))return null;
    if(va*vb<=0){
      for(let step=0;step<38;step++){
        const x=(a+b)/2,v=difference(x);if(!Number.isFinite(v))return null;
        if(Math.abs(v)<1e-10)return x;
        if((v<0)===(va<0)){a=x;va=v;}else{b=x;vb=v;}
      }
      const x=(a+b)/2;return Math.abs(difference(x))<1e-6?x:null;
    }
    return Math.abs(difference(hint))<Math.max(1e-3,domain*.02)?hint:null;
  };
  const roots=intersections.map(([x])=>refine(x)).filter((x):x is number=>x!==null&&Math.abs(x)<=domain).sort((a,b)=>a-b)
    .filter((x,index,array)=>index===0||x-array[index-1]>domain*1e-5);
  const fills:SceneFill[]=[];
  for(let interval=0;interval<roots.length-1;interval++){
    const left=roots[interval],right=roots[interval+1],steps=Math.max(24,Math.ceil((right-left)/(2*domain)*600));
    const points:number[]=[];let valid=true,previous=pair(left);
    for(let i=0;i<steps;i++){
      const a=left+(right-left)*i/steps,b=left+(right-left)*(i+1)/steps,next=pair(b),middle=pair((a+b)/2);
      if(![...previous,...next,...middle].every(Number.isFinite)||previous.some((value,k)=>Math.abs(next[k]-value)>domain*2||Math.abs(middle[k]-value)>domain*2)||((previous[0]-previous[1])*(next[0]-next[1])<0&&Math.min(Math.abs(previous[0]-previous[1]),Math.abs(next[0]-next[1]))>1e-6)){valid=false;break;}
      let polygon:Point[]=[[a,previous[0]],[b,next[0]],[b,next[1]],[a,previous[1]]];
      polygon=clipY(clipY(polygon,-domain,true),domain,false);
      for(let k=1;k<polygon.length-1;k++){
        const [p,q,r]=[polygon[0],polygon[k],polygon[k+1]];
        if(Math.abs((q[0]-p[0])*(r[1]-p[1])-(r[0]-p[0])*(q[1]-p[1]))>1e-12)points.push(...p,...q,...r);
      }
      previous=next;
    }
    if(valid&&points.length)fills.push({color:layers[interval%2].color,points});
  }
  return fills;
}
