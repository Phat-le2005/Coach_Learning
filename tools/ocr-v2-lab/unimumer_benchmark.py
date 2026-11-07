"""Real local model calls against frozen existing capture/dataset scopes; never feeds labels to inference."""
import argparse, hashlib, json, pathlib, statistics, time
from unimumer import OUT, health, infer, utc

def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true');parser.add_argument('--max-cases',type=int,default=19);parser.add_argument('--prompt',choices=['reference','strict'],default='reference');parser.add_argument('--name',default='benchmark');args=parser.parse_args()
    state=health()
    if state.get('status')!='READY':raise RuntimeError('REAL_MULTIMODAL_SERVER_NOT_READY: '+str(state))
    inputs=json.loads((OUT/'inputs.json').read_text(encoding='utf-8'))
    selected=[next(i for i in inputs if i['id']==name) for name in ['user-equation-14','mw-000aa4c444cba3f2','derivative']] if args.smoke else inputs[:args.max_cases]
    results=[];before=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest();started=utc()
    for item in selected:
        for prompt in ['reference','strict'] if args.smoke else [args.prompt]:
            png=OUT/item['imageFile']
            if hashlib.sha256(png.read_bytes()).hexdigest()!=item['inputImageHash']:raise RuntimeError('INPUT_CHANGED')
            value=infer(png,prompt,max_tokens=256)
            value.update({'id':item['id'],'sourceKind':item['sourceKind'],'scopeSource':item['scopeSource'],'annotationStatus':item['annotationStatus'],'sourceStrokeIds':item['sourceStrokeIds'],'sourceSha256':item['sourceSha256']})
            # Add evaluation reference only AFTER the local inference response exists.
            value['evaluationReference']=item.get('reference')
            results.append(value);write(args.name+'-results.json',{'startedAt':started,'updatedAt':utc(),'server':state,'inferences':results,'inputManifestHash':before,'labelsUsedInPrediction':False})
            print(json.dumps({'id':item['id'],'prompt':prompt,'status':value['status'],'ms':round(value['durationMs']),'raw':value.get('rawOutput'),'error':value.get('error')},ensure_ascii=False),flush=True)
    if before!=hashlib.sha256((OUT/'inputs.json').read_bytes()).hexdigest():raise RuntimeError('INPUT_MANIFEST_MUTATED')
    completed=[r for r in results if r['status']=='COMPLETED'];latencies=sorted(r['durationMs'] for r in completed)
    write(args.name+'-summary.json',{'status':'REAL_LOCAL_INFERENCE_EXECUTED','startedAt':started,'completedAt':utc(),'count':len(results),'completed':len(completed),'failed':len(results)-len(completed),'differentImageOutputs':len(set(r.get('rawOutput') for r in completed)),'latencyMs':{'p50':statistics.median(latencies) if latencies else None,'p95':latencies[min(len(latencies)-1,int(.95*len(latencies)))] if len(latencies)>=10 else 'NOT_MEASURED_TOO_FEW_SAMPLES'},'server':state,'noAccuracyClaimWithoutReferences':True})

    if len(completed)!=len(results):raise SystemExit(1)

if __name__=='__main__':main()
