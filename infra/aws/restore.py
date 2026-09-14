"""One-off ECS restore. Refuses an occupied target and verifies every table."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import boto3
import psycopg
from psycopg import sql


def main():
    sm = boto3.client('secretsmanager')
    master = json.loads(sm.get_secret_value(SecretId=os.environ['DB_SECRET'])['SecretString'])
    app = json.loads(sm.get_secret_value(SecretId=os.environ['APP_SECRET'])['SecretString'])
    db = os.environ['DB_NAME']
    if db not in ['aquanqa','aquanqa_live']:
        raise RuntimeError('Target not allowlisted')
    cfg = dict(host=os.environ['DB_HOST'],port=5432,user=master['username'],password=master['password'],dbname=db,sslmode='require')
    with psycopg.connect(**{**cfg,'dbname':'postgres'},autocommit=True) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s',(db,)).fetchone():
            c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
        if not c.execute("SELECT 1 FROM pg_roles WHERE rolname='aquanqa_app'").fetchone():
            c.execute(sql.SQL('CREATE ROLE aquanqa_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD {}').format(sql.Literal(app['password'])))
    with psycopg.connect(**cfg) as c:
        if c.execute("SELECT 1 FROM pg_tables WHERE schemaname IN ('core','qua','raw','stg') LIMIT 1").fetchone():
            raise RuntimeError('Target is not empty; refusing overwrite')
    s3 = boto3.client('s3')
    bucket = os.environ['BUCKET']
    prefix = 'migration/'+os.environ['BACKUP']+'/'
    for name in ['database.dump','manifest.json']:
        s3.download_file(bucket,prefix+name,'/tmp/'+name)
    manifest = json.loads(Path('/tmp/manifest.json').read_text())
    if hashlib.sha256(Path('/tmp/database.dump').read_bytes()).hexdigest()!=manifest['sha256']:
        raise RuntimeError('Dump integrity failure')
    env = dict(os.environ,PGHOST=cfg['host'],PGPORT='5432',PGUSER=cfg['user'],PGPASSWORD=cfg['password'],PGDATABASE=db,PGSSLMODE='require')
    result = subprocess.run(['pg_restore','--no-owner','--no-privileges','--exit-on-error','--single-transaction','-d',db,'/tmp/database.dump'],env=env,capture_output=True,text=True)
    if result.returncode: raise RuntimeError(result.stderr[-2500:])
    print('Restore complete; verifying all table fingerprints',flush=True)
    with psycopg.connect(**cfg) as c:
        c.execute("SET TIME ZONE 'UTC'")
        for grant in manifest['grants']: c.execute(grant)
        c.execute(sql.SQL('REVOKE CONNECT ON DATABASE {} FROM PUBLIC').format(sql.Identifier(db)))
        c.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO aquanqa_app').format(sql.Identifier(db)))
        for name,expected in manifest['tables'].items():
            schema,table = name.split('.')
            actual = c.execute(sql.SQL("SELECT count(*),md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(t)::text) h FROM {}.{} t) s").format(sql.Identifier(schema),sql.Identifier(table))).fetchone()
            if list(actual)!=expected: raise RuntimeError('Content mismatch: '+name)
        c.execute('ANALYZE')
    with psycopg.connect(**{**cfg,'user':'aquanqa_app','password':app['password']}) as c:
        count = c.execute('SELECT count(*) FROM core.ev_evaluacion').fetchone()[0]
        role = c.execute('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user').fetchone()
        if any(role): raise RuntimeError('App role is privileged')
    report = {'status':'PASS','database':db,'tables_verified':len(manifest['tables']),'evaluations':count,'sha256':manifest['sha256'],'app_role':'aquanqa_app','privileged':False}
    s3.put_object(Bucket=bucket,Key=prefix+'restore-'+db+'.json',Body=json.dumps(report).encode(),ContentType='application/json')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
