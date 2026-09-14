"""HTTP checks; mutation checks are restricted to the disposable rehearsal DB."""
import argparse
import json
from pathlib import Path
import sys
import time
from uuid import uuid4

import psycopg
import requests

from backup import render_config
from deploy import ROOT, OUT, load, save

sys.path.insert(0,str(ROOT/'backend/campo-api/src'))
from aquanqa_campo_api.core.security import encode_token


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mutations',action='store_true')
    p.add_argument('--legacy',action='store_true')
    p.add_argument('--analytics',action='store_true')
    a=p.parse_args()
    if a.mutations and (a.legacy or load('api-task')['database']!='aquanqa'):
        raise RuntimeError('Mutation checks are only allowed on the rehearsal deployment')
    _,_,env=render_config()
    with psycopg.connect(env['AQUANQA_API_DATABASE_URL']) as c:
        c.execute('SET TRANSACTION READ ONLY')
        user=c.execute('SELECT usuario_id FROM core.m_usuario WHERE activo ORDER BY usuario_id LIMIT 1').fetchone()[0]
        evaluator=c.execute('SELECT evaluador_id FROM core.m_evaluador WHERE activo AND en_maestro LIMIT 1').fetchone()[0]
        lot=c.execute('''SELECT l.lote_id FROM core.m_lote l JOIN core.m_modulo m ON m.modulo_id=l.modulo_id
        JOIN core.m_fundo f ON f.fundo_id=m.fundo_id JOIN core.m_empresa e ON e.empresa_id=f.empresa_id
        WHERE NOT l.es_sentinel AND NOT l.es_ficticio AND NOT m.es_sentinel AND NOT f.es_sentinel
        AND NOT e.es_sentinel AND m.activo AND f.activo AND e.activo LIMIT 1''').fetchone()[0]
    token=encode_token({'sub':str(user),'typ':'access','iat':int(time.time()),'exp':int(time.time())+900,'jti':str(uuid4())},env['AQUANQA_JWT_SECRET'])
    base=('https://aquanqa-campo-api.onrender.com' if a.legacy else 'https://'+load('distribution')['domain'])
    client=requests.Session();client.headers['Authorization']='Bearer '+token
    report=[]
    for endpoint in ['/v1/health/ready','/v1/auth/me','/v1/catalogos/fundos','/v1/admin/evaluaciones?page_size=1','/v1/admin/cargas?page_size=1','/openapi.json']:
        t=time.monotonic();r=client.get(base+endpoint,timeout=90)
        if r.status_code!=200: raise RuntimeError(f'{endpoint}: HTTP {r.status_code}')
        if a.legacy and r.headers.get('X-Aquanqa-Backend')!='aws': raise RuntimeError('Legacy URL is not using AWS')
        report.append({'path':endpoint,'status':r.status_code,'seconds':round(time.monotonic()-t,2)})
        print(endpoint+': PASS',flush=True)
    unauth=requests.get(base+'/v1/admin/evaluaciones',timeout=60)
    if unauth.status_code!=401: raise RuntimeError('Unauthenticated admin route did not return 401')
    print('Unauthenticated admin access denied: PASS',flush=True)
    if a.analytics:
        for module in ['estadios','flores','brotes','ramas','baya','pesos']:
            t=time.monotonic()
            r=client.get(base+'/v1/admin/evaluaciones/analitica',params={'module_key':module,'include_trend':'false'},timeout=90)
            if r.status_code!=200: raise RuntimeError(f'Analytics {module}: HTTP {r.status_code}')
            report.append({'analytics':module,'status':r.status_code,'seconds':round(time.monotonic()-t,2),'bytes':len(r.content)})
            print('Analytics '+module+': PASS',flush=True)
    if a.mutations:
        cases={'estadios':{'m1_e1':1,'m1_e2':2,'m1_e3':3,'m1_e4':4,'m1_e5':5},
               'flores':{'m2_flores':4,'m2_cuajos':3,'m2_yp':2,'m2_ya':1,'m2_ymuerta':5,'m2_brotes_tiernos':6},
               'brotes':{'m6_piso':'1','m6_brotes':7},'ramas':{'m7_ram_lt5':2,'m7_ram_gt5':3,'m7_diam100':'5.12345678'},
               'baya':{'m4_est100':'E3','m4_diam100':'12.12345678'},'pesos':{'m5_peso100':'2.12345678','m5_diam100':'12.12345678'}}
        ids=[]
        for module,values in cases.items():
            ident=str(uuid4());ids.append(ident)
            payload=dict(id=ident,module_key=module,fecha='2099-01-01',captured_at='2099-01-01T15:30:00Z',lote_id=lot,evaluador_id=evaluator,cortina=1,hilera=1,planta=1,valores=values)
            r=client.post(base+'/v1/evaluaciones',json=payload,timeout=90)
            if r.status_code!=201: raise RuntimeError(f'{module} create: HTTP {r.status_code}')
            r=client.post(base+'/v1/evaluaciones',json=payload,timeout=90)
            if r.status_code!=200 or r.json()['status']!='duplicate': raise RuntimeError(module+' idempotency failure')
            r=client.patch(base+'/v1/evaluaciones/'+ident,json={**payload,'planta':2},timeout=90)
            if r.status_code!=200: raise RuntimeError(f'{module} patch: HTTP {r.status_code}')
            r=client.get(base+'/v1/evaluaciones/historial',params={'evaluador_id':evaluator,'module_key':module,'limit':5},timeout=90)
            if r.status_code!=200 or not any(x['id']==ident for x in r.json()['items']): raise RuntimeError(module+' history failure')
            print(module+': create/retry/edit/history PASS',flush=True)
        save('rehearsal-test-ids',ids)
    save('smoke-legacy' if a.legacy else ('smoke-rehearsal' if a.mutations else 'smoke-production'),{'base':base,'checks':report,'unauthorized_status':unauth.status_code,'mutations':a.mutations})


if __name__=='__main__': main()
