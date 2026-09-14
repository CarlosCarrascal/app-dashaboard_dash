"""Publish a deployment snapshot through an isolated git index.

The user's current branch, index and unrelated local files are not modified.
"""
import os
import subprocess
from uuid import uuid4

from deploy import OUT, ROOT, save

BRANCH = 'codex/aws-production-20260914'


def main():
    index = OUT/('release-'+uuid4().hex+'.index')
    env = dict(os.environ,GIT_INDEX_FILE=str(index))
    def git(*args, **kw):
        return subprocess.run(['git',*args],cwd=ROOT,env=env,capture_output=True,text=True,check=True,**kw).stdout.strip()
    existing=subprocess.run(['git','rev-parse','--verify','refs/heads/'+BRANCH],cwd=ROOT,capture_output=True,text=True)
    parent=existing.stdout.strip() if existing.returncode==0 else git('rev-parse','HEAD')
    git('read-tree',parent)
    git('add','--','backend/campo-api','frontend','infra/aws','docs/api/openapi-v1.json')
    names=git('diff','--cached','--name-only',parent).splitlines()
    if any('/node_modules/' in n or n.endswith(('.dump','.pgpass','.zip')) or n.split('/')[-1] in ['.env','.env.local','credentials'] for n in names):
        raise RuntimeError('Unexpected artifact in deployment snapshot')
    tree=git('write-tree')
    commit=git('commit-tree',tree,'-p',parent,input='Deploy API and Angular to AWS with verified PostgreSQL migration\n')
    git('update-ref','refs/heads/'+BRANCH,commit,parent if existing.returncode==0 else '0'*40)
    git('push','origin',BRANCH)
    save('release',{'branch':BRANCH,'commit':commit,'parent':parent,'changed_files':len(names)})
    print('Published deployment branch:',BRANCH,'commit:',commit,'files:',len(names))


if __name__ == '__main__':
    main()
