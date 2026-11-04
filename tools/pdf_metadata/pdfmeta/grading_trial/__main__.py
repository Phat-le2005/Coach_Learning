import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description='Source-reviewed calculus sandbox, never production grading')
    p.add_argument('action',choices=['build','evaluate','check','all'])
    p.add_argument('--job',type=Path,required=True);p.add_argument('--cohort',type=Path)
    p.add_argument('--request',type=Path);args=p.parse_args()
    if args.action in {'build','all'}:
        if args.cohort is None:p.error('--cohort is required')
        from .build import build
        result=build(args.job,args.cohort)
    if args.action in {'evaluate','all'}:
        from .scenarios import run
        result=run(args.job)
    if args.action=='check':
        if args.request is None:p.error('--request is required')
        from .build import check
        result=check(args.job,json.loads(args.request.read_text(encoding='utf-8')))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result.get('assertions_failed'):raise SystemExit(2)


if __name__=='__main__':main()
