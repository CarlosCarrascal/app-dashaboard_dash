"""Consistent, read-only export of the database currently configured in Render."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

import psycopg
from psycopg import sql
import requests
import yaml

from deploy import OUT, session, ACCOUNT, REGION

SCHEMAS = ['core', 'qua', 'raw', 'stg', 'public']


def render_config():
    key = yaml.safe_load((Path.home()/'.render/cli.yaml').read_text())['api']['key']
    h = {'Authorization': 'Bearer ' + key}
    b = 'https://api.render.com/v1/services/srv-dabjfup5efls73djvhs0'
    r = requests.get(b + '/env-vars', headers=h, params={'limit': 100}, timeout=30)
    r.raise_for_status()
    return b, h, {v['envVar']['key']: v['envVar']['value'] for v in r.json()}


def backup(label):
    _, _, env = render_config()
    uri = env['AQUANQA_API_DATABASE_URL']
    path = OUT / label
    path.mkdir(exist_ok=True)
    if (path/'database.dump').exists():
        raise RuntimeError('Backup exists; choose a new label')
    grants = []
    with psycopg.connect(uri, connect_timeout=30) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute("SET LOCAL TIME ZONE 'UTC'")
        tables = c.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname=ANY(%s) ORDER BY 1,2", (SCHEMAS,)).fetchall()
        snapshot = c.execute('SELECT pg_export_snapshot()').fetchone()[0]
        dsn = psycopg.conninfo.conninfo_to_dict(uri)
        process_env = dict(os.environ, PGHOST=dsn['host'], PGPORT=dsn.get('port','5432'),
                           PGUSER=dsn['user'], PGPASSWORD=dsn['password'], PGDATABASE=dsn['dbname'], PGSSLMODE='require')
        args = ['C:/Program Files/PostgreSQL/18/bin/pg_dump.exe','-w','-Fc','--no-owner','--no-privileges','--snapshot',snapshot,'-f',str(path/'database.dump')]
        result = subprocess.run(args,env=process_env,capture_output=True,text=True)
        if result.returncode: raise RuntimeError(result.stderr[-2000:])
        counts = {}
        for schema, table in tables:
            counts[schema+'.'+table] = c.execute(sql.SQL("SELECT count(*), md5(coalesce(string_agg(h,'' ORDER BY h),'')) FROM (SELECT md5(to_jsonb(t)::text) h FROM {}.{} t) s").format(sql.Identifier(schema),sql.Identifier(table))).fetchone()
        for schema in SCHEMAS:
            grants.append(sql.SQL('REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC').format(sql.Identifier(schema)).as_string(c)+';')
        for schema,priv in c.execute("SELECT nspname,a.privilege_type FROM pg_namespace n CROSS JOIN LATERAL aclexplode(n.nspacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE r.rolname='aquanqa_app' AND nspname=ANY(%s)",(SCHEMAS,)):
            grants.append(sql.SQL('GRANT {} ON SCHEMA {} TO aquanqa_app;').format(sql.SQL(priv),sql.Identifier(schema)).as_string(c))
        for schema,name,kind,priv in c.execute("SELECT n.nspname,c.relname,c.relkind,a.privilege_type FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE r.rolname='aquanqa_app' AND n.nspname=ANY(%s)",(SCHEMAS,)):
            grants.append(sql.SQL('GRANT {} ON {} {}.{} TO aquanqa_app;').format(sql.SQL(priv),sql.SQL('SEQUENCE' if kind=='S' else 'TABLE'),sql.Identifier(schema),sql.Identifier(name)).as_string(c))
        for schema,table,col,priv in c.execute("SELECT n.nspname,c.relname,at.attname,a.privilege_type FROM pg_attribute at JOIN pg_class c ON c.oid=at.attrelid JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(at.attacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE r.rolname='aquanqa_app' AND n.nspname=ANY(%s)",(SCHEMAS,)):
            grants.append(sql.SQL('GRANT {} ({}) ON {}.{} TO aquanqa_app;').format(sql.SQL(priv),sql.Identifier(col),sql.Identifier(schema),sql.Identifier(table)).as_string(c))
        for signature,kind in c.execute("SELECT p.oid::regprocedure::text,p.prokind FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=ANY(%s) AND has_function_privilege('aquanqa_app',p.oid,'EXECUTE')",(SCHEMAS,)):
            grants.append(f"GRANT EXECUTE ON {'PROCEDURE' if kind=='p' else 'FUNCTION'} {signature} TO aquanqa_app;")
        manifest = {'label':label,'tables':counts,'grants':grants,'sha256':hashlib.sha256((path/'database.dump').read_bytes()).hexdigest(),'database':dsn['dbname']}
        (path/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    s = session()
    # Upload only after the infrastructure stack exposes its artifact bucket.
    bucket = f'aquanqa-{ACCOUNT}-{REGION}-artifacts'
    for name in ['database.dump','manifest.json']:
        s.client('s3').upload_file(str(path/name),bucket,'migration/'+label+'/'+name)
    print(json.dumps({'backup':label,'tables':len(counts),'bytes':(path/'database.dump').stat().st_size,'sha256':manifest['sha256']}))


if __name__ == '__main__':
    import sys
    backup(sys.argv[1])
