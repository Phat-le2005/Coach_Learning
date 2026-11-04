"""One short-lived, locally supervised transcription chunk."""
import argparse
from pathlib import Path
import traceback

from ...storage import read_json, write_json
from .engine import worker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', type=Path, required=True)
    args = parser.parse_args()
    task = read_json(args.task)
    try:
        result = worker(task['items'], task['documents'], task['output'], task['runtime'],
                        task['katex'], task['identity'], task['cache_index'], task['options'])
        write_json(args.task.with_name('result.json'), result)
        return 0 if result['completed'] == len(task['items']) else 1
    except BaseException as error:
        write_json(args.task.with_name('result.json'), {
            'completed': 0, 'error': type(error).__name__ + ': ' + str(error),
            'traceback': traceback.format_exc(),
        })
        raise


if __name__ == '__main__':
    raise SystemExit(main())
