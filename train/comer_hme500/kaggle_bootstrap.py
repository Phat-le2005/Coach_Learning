"""Clone/update the training checkout without placing GH_TOKEN in URLs or Git config."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit


def checkout_repo(repo_url, branch, destination, token=None):
    parsed = urlsplit(repo_url)
    if (parsed.scheme != 'https' or parsed.hostname != 'github.com'
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or len(parsed.path.strip('/').removesuffix('.git').split('/')) != 2):
        raise ValueError('Expected a plain https://github.com/owner/repo.git URL, without credentials.')
    if not branch or branch.startswith('-') or any(c.isspace() for c in branch):
        raise ValueError('Invalid Git branch.')
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    # GH_TOKEN exists only in Git's child environment, not in the training process.
    env.pop('GH_TOKEN', None)
    env.pop('GITHUB_TOKEN', None)
    env['GIT_TERMINAL_PROMPT'] = '0'
    with tempfile.TemporaryDirectory(prefix='coach-comer-git-') as temporary:
        if token:
            askpass = Path(temporary)/'askpass.sh'
            askpass.write_text('#!/bin/sh\ncase "$1" in\n'
                '  *sername*) printf "%s\\n" "x-access-token" ;;\n'
                '  *assword*) printf "%s\\n" "$COACH_GIT_TOKEN" ;;\n'
                '  *) exit 1 ;;\nesac\n', encoding='utf-8')
            askpass.chmod(0o700)
            env['GIT_ASKPASS'] = str(askpass)
            env['COACH_GIT_TOKEN'] = token
        else:
            env.pop('COACH_GIT_TOKEN', None)

        def git(*args):
            try:
                p = subprocess.run(['git', '-c', 'credential.helper=', *map(str,args)],
                    env=env, text=True, encoding='utf-8', capture_output=True, check=True)
                return p.stdout.strip()
            except subprocess.CalledProcessError:
                # Git/auth stderr is not copied into notebook output.
                raise RuntimeError('Git operation failed. Check Internet, repo/branch and GH_TOKEN access. '
                                   'No token or authentication output has been printed.') from None

        if destination.exists():
            if not (destination/'.git').exists():
                raise RuntimeError('Destination exists but is not a Git checkout; choose another REPO_PATH.')
            origin = urlsplit(git('-C', destination, 'remote', 'get-url', 'origin'))
            if origin.username or origin.password:
                raise RuntimeError('Existing origin contains credentials; use a fresh REPO_PATH.')
            if origin.hostname != parsed.hostname or origin.path.removesuffix('.git') != parsed.path.removesuffix('.git'):
                raise RuntimeError('Existing checkout belongs to another repository.')
            if git('-C', destination, 'status', '--porcelain'):
                raise RuntimeError('Checkout has local edits; keep them and choose a new REPO_PATH.')
            if git('-C', destination, 'branch', '--show-current') != branch:
                raise RuntimeError('Checkout branch differs from GITHUB_REPO_BRANCH; choose a new REPO_PATH.')
            git('-C', destination, 'pull', '--ff-only', 'origin', branch)
        else:
            git('clone', '--depth', '1', '--filter=blob:none', '--sparse',
                '--branch', branch, repo_url, destination)
            git('-C', destination, 'sparse-checkout', 'set', 'train/comer_hme500')
        revision = git('-C', destination, 'rev-parse', 'HEAD')
    lab = destination/'train/comer_hme500'
    if not (lab/'scripts/run_kaggle.sh').is_file():
        raise RuntimeError('This Git revision lacks scripts/run_kaggle.sh; check the pushed branch.')
    return lab, revision
