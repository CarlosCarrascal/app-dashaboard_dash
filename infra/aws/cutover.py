"""Explicit production cutover steps; never enables dual database writes."""
import argparse
from datetime import datetime, timezone
import json

import psycopg
from psycopg import sql
import requests

from backup import render_config
from deploy import session, outputs, load, save, OUT, REGION


def freeze(s):
    if (OUT/'source-frozen.json').exists(): raise RuntimeError('Source freeze already recorded')
    if not (OUT/'smoke-rehearsal.json').exists(): raise RuntimeError('Rehearsal HTTP checks are required')
    b,h,e=render_config()
    r=requests.get(b,headers=h,timeout=30);r.raise_for_status()
    sm=s.client('secretsmanager')
    sm.create_secret(Name='aquanqa/production/render-before-cutover',SecretString=json.dumps({'service':r.json(),'environment':e}),Tags=[{'Key':'Project','Value':'aquanqa'}])
    o=outputs(s);elb=s.client('elbv2')
    listener=elb.describe_listeners(LoadBalancerArn=o['LoadBalancer'])['Listeners'][0]['ListenerArn']
    health=elb.create_rule(ListenerArn=listener,Priority=1,Conditions=[{'Field':'path-pattern','Values':['/v1/health/*']}],Actions=[{'Type':'forward','TargetGroupArn':o['TargetGroup']}])['Rules'][0]['RuleArn']
    maintenance=elb.create_rule(ListenerArn=listener,Priority=2,Conditions=[{'Field':'path-pattern','Values':['/v1/*']}],Actions=[{'Type':'fixed-response','FixedResponseConfig':{'StatusCode':'503','ContentType':'application/json','MessageBody':'{"detail":"Migracion en curso. Reintenta la sincronizacion en unos minutos."}'}}])['Rules'][0]['RuleArn']
    save('maintenance',{'health':health,'rule':maintenance})
    with psycopg.connect(e['AQUANQA_API_DATABASE_URL'],autocommit=True) as c:
        db,role=c.execute('SELECT current_database(),current_user').fetchone()
        if db!='neondb' or role!='neondb_owner': raise RuntimeError('Unexpected source')
        c.execute(sql.SQL('ALTER ROLE {} IN DATABASE {} SET default_transaction_read_only=on').format(sql.Identifier(role),sql.Identifier(db)))
        c.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s AND usename=%s AND pid<>pg_backend_pid()',(db,role))
    with psycopg.connect(e['AQUANQA_API_DATABASE_URL']) as c:
        if c.execute('SHOW transaction_read_only').fetchone()[0]!='on': raise RuntimeError('Source is not read-only')
    save('source-frozen',{'time':datetime.now(timezone.utc).isoformat(),'database':db,'role':role})
    print('Source is read-only; AWS mutations are temporarily paused')


def proxy(s):
    if not (OUT/'source-frozen.json').exists(): raise RuntimeError('Freeze source writes first')
    rule=s.client('elbv2').describe_rules(RuleArns=[load('maintenance')['rule']])['Rules'][0]
    if rule['Actions'][0].get('FixedResponseConfig',{}).get('StatusCode')!='503':
        raise RuntimeError('Maintenance gate must remain active while deploying the proxy')
    b,h,e=render_config()
    url='https://'+load('distribution')['domain']
    # Preserve environment variables until post-cutover validation and rollback review.
    e['AQUANQA_UPSTREAM_URL']=url
    r=requests.put(b+'/env-vars',headers=h,json=[{'key':k,'value':v} for k,v in e.items()],timeout=30);r.raise_for_status()
    patch={'branch':load('release')['branch'],'autoDeploy':'no','rootDir':'infra/aws/render-proxy','serviceDetails':{'envSpecificDetails':{'buildCommand':'pip install -r requirements.txt','startCommand':'python -m uvicorn app:app --host 0.0.0.0 --port $PORT'},'healthCheckPath':'/v1/health/live'}}
    r=requests.patch(b,headers=h,json=patch,timeout=30);r.raise_for_status()
    r=requests.post(b+'/deploys',headers=h,json={'clearCache':'clear'},timeout=30);r.raise_for_status()
    d=r.json();save('render-deploy',{'id':d['id'],'upstream':url})
    print('Compatibility proxy deploy started:',d['id'])


def proxy_status(s):
    b,h,_=render_config()
    r=requests.get(b+'/deploys/'+load('render-deploy')['id'],headers=h,timeout=30);r.raise_for_status()
    print(r.json()['status'])


def open_traffic(s):
    if load('api-task')['database']!='aquanqa_live': raise RuntimeError('Not on the production database')
    o=outputs(s)
    d=s.client('ecs').describe_services(cluster=o['Cluster'],services=['aquanqa-api'])['services'][0]
    if len(d['deployments'])!=1 or d['deployments'][0].get('rolloutState')!='COMPLETED' or d['runningCount']!=2:
        raise RuntimeError('Wait for both production tasks and old task drainage')
    b,h,_=render_config()
    r=requests.get(b+'/deploys/'+load('render-deploy')['id'],headers=h,timeout=30);r.raise_for_status()
    if r.json()['status']!='live': raise RuntimeError('Render proxy is not live')
    # Verify the original URL reaches AWS even while application routes are paused.
    r=requests.get('https://aquanqa-campo-api.onrender.com/v1/health/ready',timeout=90)
    if r.status_code!=200 or r.headers.get('X-Aquanqa-Backend')!='aws': raise RuntimeError('Legacy proxy health check failed')
    rules=load('maintenance')
    s.client('elbv2').delete_rule(RuleArn=rules['rule'])
    s.client('elbv2').delete_rule(RuleArn=rules['health'])
    save('cutover-complete',{'time':datetime.now(timezone.utc).isoformat(),'database':'aquanqa_live','legacy':'https://aquanqa-campo-api.onrender.com','url':load('distribution')['domain']})
    print('Production traffic enabled; both URLs use AWS/RDS, Neon remains read-only')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','proxy','proxy_status','open_traffic'])
    globals()[p.parse_args().command](session())
