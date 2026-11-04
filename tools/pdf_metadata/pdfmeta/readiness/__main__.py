import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description='Local PDF image checks, batch and provisional core export')
    commands=p.add_subparsers(dest='action',required=True)
    for name in ['visual','export','check','all']:
        c=commands.add_parser(name);c.add_argument('--job',type=Path,required=True)
        if name in {'visual','all'}:
            c.add_argument('--runtime',type=Path,required=True);c.add_argument('--limit',type=int,default=12)
            c.add_argument('--retry-failed',action='store_true')
            c.add_argument('--engine',choices=['ocr','qwen'],default='ocr')
        if name=='check':c.add_argument('--request',type=Path,required=True)
    c=commands.add_parser('batch');c.add_argument('inputs',nargs='+',type=Path)
    c.add_argument('--repo',type=Path,required=True);c.add_argument('--storage',type=Path,required=True)
    c.add_argument('--review-limit',type=int,default=3);c.add_argument('--visual-limit',type=int,default=8)
    c.add_argument('--max-pages',type=int,default=100);c.add_argument('--max-pdfs',type=int,default=0)
    c.add_argument('--timeout',type=int,default=3600);c.add_argument('--skip-qwen',action='store_true')
    c.add_argument('--retry-failed',action='store_true')
    c.add_argument('--oversize-policy',choices=['run','defer'],default='run')
    c=commands.add_parser('evaluate');c.add_argument('--queue',type=Path,required=True);c.add_argument('--manifest',type=Path)
    args=vars(p.parse_args());action=args.pop('action')
    if action=='evaluate':
        from .evaluation import evaluate
        result=evaluate(args['queue'],manifest=args['manifest'])
    elif action=='batch':
        from .batch import run
        result=run(**args)
    elif action in {'visual','all'}:
        from .visual import run
        result={'image':run(**args)}
        if action=='all':
            from .core import export
            result['core']=export(args['job'])
    else:
        from .core import export,check
        result=export(args['job']) if action=='export' else check(args['job'],json.loads(args['request'].read_text(encoding='utf-8')))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
