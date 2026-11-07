"""Bounded, resumable official downloads for the isolated Uni-MuMER experiment."""
import argparse, concurrent.futures, hashlib, json, pathlib, time, urllib.request, zipfile, zlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / '.tmp/tri-unimumer-lab'
CACHE = OUT / 'cache'
REPOSITORY = 'mradermacher/Uni-MuMER-Qwen3.5-2B-GGUF'
REVISION = '9451fe296d68348d751adc6e71e32be810e6f489'
MODEL_FILES = {
    'Uni-MuMER-Qwen3.5-2B.Q4_K_M.gguf': (1274397280, '05eaa7c1593c1ba52d7b9ee848bd8303523be764e781aec9cb88a4442198f680'),
    'Uni-MuMER-Qwen3.5-2B.mmproj-Q8_0.gguf': (364664704, 'a6b5c31b91655f23cfba7828eeeb992cefcc99ae75f45580187af674b6cbce28'),
}

def checksum(file):
    digest = hashlib.sha256()
    with file.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''): digest.update(block)
    return digest.hexdigest()

def download(url, target, size, digest):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size == size and checksum(target) == digest: return
        raise RuntimeError('Existing completed asset failed checksum; preserved: ' + str(target))
    partial = target.with_suffix(target.suffix+'.part')
    if size > 100_000_000:
        return ranged_download(url, target, size, digest, partial)
    for attempt in range(6):
        offset = partial.stat().st_size if partial.exists() else 0
        if offset == size: break
        if offset > size: raise RuntimeError('Partial exceeds declared size')
        headers = {'User-Agent': 'CoachLearning-local-research'}
        if offset: headers['Range'] = f'bytes={offset}-'
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
                if offset and response.status != 206: raise RuntimeError('Server did not honor resume range')
                if offset and not response.headers.get('Content-Range', '').startswith(f'bytes {offset}-'): raise RuntimeError('Resume offset mismatch')
                written = offset; last = written
                with partial.open('ab' if offset else 'wb') as stream:
                    while True:
                        block = response.read(2*1024*1024)
                        if not block: break
                        written += len(block)
                        if written > size: raise RuntimeError('Download larger than manifest')
                        stream.write(block)
                        if written-last > 64*1024*1024:
                            print(f'{target.name}: {written}/{size}', flush=True); last=written
            if partial.stat().st_size == size: break
        except Exception as error:
            print(f'Retry {attempt+1}: {target.name}: {type(error).__name__}: {error}', flush=True)
            if attempt == 5: raise
            time.sleep(2)
    if not partial.exists() or partial.stat().st_size != size or checksum(partial) != digest: raise RuntimeError('Incomplete or checksum mismatch: '+target.name)
    partial.rename(target)
    print('SHA256_VERIFIED '+target.name, flush=True)

def ranged_download(url, target, size, digest, partial):
    """Four bounded HTTP ranges, each resumable; keep pre-existing sequential prefix."""
    prefix = partial.stat().st_size if partial.exists() else 0
    if prefix > size: raise RuntimeError('Partial exceeds manifest')
    chunks = target.parent / (target.name+'.segments'); chunks.mkdir(exist_ok=True)
    # Persist the original prefix length so retries never shift segment identity.
    meta = chunks/'ranges.json'
    if meta.exists(): prefix=json.loads(meta.read_text())['prefix']
    else: meta.write_text(json.dumps({'prefix':prefix,'size':size,'sha256':digest}))
    ranges=[(start,min(size-1,start+16*1024*1024-1)) for start in range(prefix,size,16*1024*1024)]
    def part(pair):
        start,end=pair; file=chunks/f'{start}-{end}.part'; expected=end-start+1
        for attempt in range(6):
            offset=file.stat().st_size if file.exists() else 0
            if offset==expected:return file
            if offset>expected:raise RuntimeError('Oversized range segment')
            try:
                request=urllib.request.Request(url,headers={'User-Agent':'CoachLearning-local-research','Range':f'bytes={start+offset}-{end}'})
                with urllib.request.urlopen(request,timeout=90) as response:
                    if response.status!=206 or not response.headers.get('Content-Range','').startswith(f'bytes {start+offset}-'):raise RuntimeError('Range not honored')
                    with file.open('ab') as stream:
                        while True:
                            data=response.read(min(1024*1024,expected-offset+1))
                            if not data:break
                            offset+=len(data)
                            if offset>expected:raise RuntimeError('Range too large')
                            stream.write(data)
                if offset==expected:return file
            except Exception as error:
                if attempt==5:raise
                time.sleep(1)
        raise RuntimeError('Range incomplete')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        completed=0
        for _ in pool.map(part,ranges):
            completed+=1
            if completed%4==0:print(f'{target.name}: verified transfer {completed}/{len(ranges)} ranges',flush=True)
    assembled=target.with_suffix(target.suffix+'.assembled')
    with assembled.open('wb') as stream:
        if prefix:
            with partial.open('rb') as original:
                remaining=prefix
                while remaining:
                    data=original.read(min(2*1024*1024,remaining))
                    if not data:raise RuntimeError('Sequential prefix incomplete')
                    stream.write(data);remaining-=len(data)
        for pair in ranges:
            with (chunks/f'{pair[0]}-{pair[1]}.part').open('rb') as segment:
                for data in iter(lambda:segment.read(2*1024*1024),b''):stream.write(data)
    if assembled.stat().st_size!=size or checksum(assembled)!=digest:raise RuntimeError('Assembled checksum mismatch')
    assembled.rename(target);print('SHA256_VERIFIED '+target.name,flush=True)

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--runtime", choices=["cpu", "cuda", "both"], default="cpu"); args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    # Bootstrap pinned official metadata when replaying without local research artifacts.
    for name, url in [
        ('gguf-metadata.json', f'https://huggingface.co/api/models/{REPOSITORY}/revision/{REVISION}?blobs=true'),
        ('runtime-binary-release.json', 'https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b11960'),
    ]:
        target = OUT/name
        if not target.exists():
            req = urllib.request.Request(url, headers={'User-Agent':'CoachLearning-local-research'})
            with urllib.request.urlopen(req, timeout=60) as response: payload=json.load(response)
            target.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    metadata = json.loads((OUT/'gguf-metadata.json').read_text())
    if metadata['sha'] != REVISION or metadata['cardData']['license'] != 'apache-2.0': raise RuntimeError('Model revision/license differs from audited metadata')
    assets=[]
    for name,(size,digest) in MODEL_FILES.items():
        listed = next(f for f in metadata['siblings'] if f['rfilename']==name)
        if listed['lfs']['sha256'] != digest or listed['size'] != size: raise RuntimeError('LFS identity mismatch')
        url=f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}'
        download(url,CACHE/'models'/name,size,digest)
        assets.append({'name':name,'repository':REPOSITORY,'revision':REVISION,'bytes':size,'sha256':digest,'license':'Apache-2.0','url':url})
    release=json.loads((OUT/'runtime-binary-release.json').read_text())
    names=['llama-b11960-bin-win-cuda-12.4-x64.zip','cudart-llama-bin-win-cuda-12.4-x64.zip','llama-b11960-bin-win-cpu-x64.zip']
    for name in names:
        if args.runtime == 'cpu' and ('cuda' in name or 'cudart' in name): continue
        if args.runtime == 'cuda' and '-cpu-' in name: continue
        asset=next(a for a in release['assets'] if a['name']==name)
        digest=asset['digest'].removeprefix('sha256:')
        archive=CACHE/'downloads'/name; download(asset['browser_download_url'],archive,asset['size'],digest)
        destination=CACHE/('llama-cpu' if 'win-cpu' in name else 'llama-cuda')
        destination.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            if z.testzip() is not None: raise RuntimeError('Invalid runtime ZIP')
            for member in z.infolist():
                target=(destination/member.filename).resolve()
                if not target.is_relative_to(destination.resolve()): raise RuntimeError('Unsafe runtime archive path')
                if member.file_size > 2_000_000_000: raise RuntimeError('Runtime member too large')
                # Idempotent setup must not rewrite DLLs used by a running server.
                if target.is_file() and target.stat().st_size == member.file_size:
                    crc = 0
                    with target.open('rb') as existing:
                        for block in iter(lambda: existing.read(2*1024*1024), b''): crc = zlib.crc32(block, crc)
                    if crc == member.CRC: continue
                z.extract(member,destination)
        assets.append({'name':name,'bytes':asset['size'],'sha256':digest,'url':asset['browser_download_url'],'tag':release['tag_name'],'commit':release['target_commitish'],'license':'MIT (llama.cpp); CUDA runtime redistribution terms included in package'})
    (OUT/'download-manifest.json').write_text(json.dumps({'assets':assets,'completedAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'weightsInGit':False},indent=2))
    print('ALL_ASSETS_VERIFIED',flush=True)

if __name__=='__main__': main()
