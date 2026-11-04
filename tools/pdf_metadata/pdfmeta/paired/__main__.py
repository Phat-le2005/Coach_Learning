import argparse
import json
from pathlib import Path

from .dataset import build, export


def main():
    parser = argparse.ArgumentParser(description='One source-first HTML with question/solution metadata; no inference')
    sub = parser.add_subparsers(dest='action', required=True)
    convert = sub.add_parser('convert'); convert.add_argument('--pdf', type=Path, required=True)
    convert.add_argument('--jobs', type=Path, required=True)
    metadata = sub.add_parser('metadata'); metadata.add_argument('--html', type=Path, required=True)
    metadata.add_argument('--output', type=Path, required=True)
    prep = sub.add_parser('quality-prepare'); prep.add_argument('--job', type=Path, required=True)
    prep.add_argument('--selection', type=Path, required=True); prep.add_argument('--output', type=Path, required=True)
    review = sub.add_parser('quality-run'); review.add_argument('--job', type=Path, required=True)
    review.add_argument('--prepared', type=Path, required=True); review.add_argument('--runtime', type=Path, required=True)
    collection = sub.add_parser('solved-collection'); collection.add_argument('--job', type=Path, required=True)
    collection.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'convert':
        from ..storage import file_hash
        result = build(args.pdf, args.jobs / file_hash(args.pdf)[:24])
    elif args.action == 'metadata':
        result = export(args.html, args.output)
    elif args.action == 'quality-prepare':
        from .quality import prepare
        result = prepare(args.job, args.selection, args.output)
        result = {k: v for k, v in result.items() if k != 'regions'} | {'regions': len(result['regions'])}
    elif args.action == 'quality-run':
        from .quality import run
        result = run(args.job, args.prepared, args.runtime)
    else:
        from .collection import collect
        result = collect(args.job, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
