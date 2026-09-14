"""Create a dedicated read-only login and local pgAdmin import, without printing secrets."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import urllib.request
import psycopg
from psycopg import sql
from deploy import session, outputs

s = session()
o = outputs(s)
folder = Path(os.environ['APPDATA']) / 'Aquanqa' / 'pgadmin'
folder.mkdir(parents=True, exist_ok=True)
identity = subprocess.check_output(['whoami'], text=True).strip()
subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r', identity + ':(OI)(CI)F'], check=True, capture_output=True)
certificate = folder / 'us-east-1-bundle.pem'
urllib.request.urlretrieve('https://truststore.pki.rds.amazonaws.com/us-east-1/us-east-1-bundle.pem', certificate)
master = json.loads(s.client('secretsmanager').get_secret_value(SecretId=o['DbSecret'])['SecretString'])
username = 'aquanqa_consulta'
passfile = folder / 'pgpass.conf'
password = secrets.token_urlsafe(32)
with psycopg.connect(host=o['DbHost'], dbname='aquanqa_live', user=master['username'], password=master['password'], sslmode='verify-full', sslrootcert=str(certificate), connect_timeout=15) as c:
    exists = c.execute('SELECT 1 FROM pg_roles WHERE rolname=%s', (username,)).fetchone()
    if exists:
        if not passfile.exists():
            raise RuntimeError('Read-only role already exists; refusing to reset its password')
        password = passfile.read_text().strip().rsplit(':', 1)[1]
    else:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION').format(sql.Identifier(username), sql.Literal(password)))
    c.execute(sql.SQL('GRANT CONNECT ON DATABASE aquanqa_live TO {}').format(sql.Identifier(username)))
    c.execute(sql.SQL('GRANT USAGE ON SCHEMA core, raw, stg, qua, public TO {}').format(sql.Identifier(username)))
    c.execute(sql.SQL('GRANT SELECT ON ALL TABLES IN SCHEMA core, raw, stg, qua, public TO {}').format(sql.Identifier(username)))
    c.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(username)))
    c.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '60s'").format(sql.Identifier(username)))
passfile.write_text(f"{o['DbHost']}:5432:aquanqa_live:{username}:{password}\n", encoding='utf-8')
config = {'Servers': {'1': {'Name': 'Aquanqa AWS - solo lectura', 'Group': 'AWS Produccion', 'Host': o['DbHost'], 'Port': 5432, 'MaintenanceDB': 'aquanqa_live', 'Username': username, 'SSLMode': 'verify-full', 'SSLRootCert': str(certificate), 'PassFile': str(passfile), 'DBRestriction': 'aquanqa_live', 'Comment': 'Conexion directa desde IP autorizada; usuario de consulta.'}}}
(folder / 'servers.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
with psycopg.connect(host=o['DbHost'], dbname='aquanqa_live', user=username, passfile=str(passfile), sslmode='verify-full', sslrootcert=str(certificate), connect_timeout=15) as c:
    print('Connection:', c.execute('SELECT current_database(), current_user').fetchone())
    print('SSL:', c.execute('SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()[0])
    print('Visible tables:', c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema IN ('core','raw','stg','qua','public')").fetchone()[0])
    print('User-table write permission:', c.execute("SELECT has_table_privilege(current_user,'core.m_usuario','UPDATE')").fetchone()[0])
print('pgAdmin import:', folder / 'servers.json')
