"""Commit only Cloudflare deployment files on the existing release branch."""
import os
from pathlib import Path
import subprocess
from uuid import uuid4

root = Path(__file__).resolve().parents[2]
branch = 'codex/aws-production-20260914'
index = root / 'data/salida' / ('cloudflare-index-' + uuid4().hex)
environment = dict(os.environ, GIT_INDEX_FILE=str(index))
def git(*args, **kwargs):
    return subprocess.run(['git', *args], cwd=root, env=environment, capture_output=True, text=True, check=True, **kwargs).stdout.strip()
parent = git('rev-parse', 'refs/heads/' + branch)
git('read-tree', parent)
git('add', '--', 'infra/cloudflare')
tree = git('write-tree')
commit = git('commit-tree', tree, '-p', parent, input='Publish Angular on Cloudflare Pages with same-origin AWS API proxy\n')
git('update-ref', 'refs/heads/' + branch, commit, parent)
git('push', 'origin', branch)
print('Published', branch, commit)
