"""Fetch an exact public CoMER revision, verifying Git blob identities."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

LOCK = Path(__file__).with_name('upstream.lock.json')
DEFAULT = Path(__file__).resolve().parents[1] / '.cache/upstream'

def blob_hash(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def fetch(destination: Path = DEFAULT) -> dict:
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    report = {'repository': lock['repository'], 'commit': lock['commit'], 'files': []}
    for entry in lock['files']:
        target = (destination / entry['path']).resolve()
        if not target.is_relative_to(destination):
            raise ValueError('Upstream path escapes destination')
        if target.exists():
            data = target.read_bytes()
            if blob_hash(data) != entry['sha']:
                raise ValueError(f"Existing upstream file changed: {entry['path']}")
        else:
            url = f"https://raw.githubusercontent.com/Green-Wood/CoMER/{lock['commit']}/{quote(entry['path'])}"
            req = Request(url, headers={'User-Agent': 'CoachLearning-CoMER-lab'})
            with urlopen(req, timeout=120) as response:
                data = response.read(entry['size'] + 1)
            if len(data) != entry['size'] or blob_hash(data) != entry['sha']:
                raise ValueError(f"Upstream integrity mismatch: {entry['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            pending=target.with_name(target.name+'.download')
            pending.write_bytes(data)
            pending.replace(target)
        report['files'].append({'path': entry['path'], 'bytes': len(data),
                                'sha256': hashlib.sha256(data).hexdigest(), 'git_blob': entry['sha']})
        print(entry['path'], len(data), flush=True)
    (destination / 'download-manifest.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=DEFAULT)
    fetch(parser.parse_args().destination)
