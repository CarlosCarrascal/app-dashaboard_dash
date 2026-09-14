from datetime import date
from fastapi.testclient import TestClient
from aquanqa_campo_api.main import app
from aquanqa_campo_api.api.dependencies import get_admin_repository, get_admin_user
from aquanqa_campo_api.modules.admin.analytics import AnalyticsQuery, build_analytics
from aquanqa_campo_api.modules.admin.schemas import AdminEvaluationDetail
from aquanqa_campo_api.modules.seguridad.schemas import AuthUser

class Repository:
    calls=0
    def evaluation_analytics(self, query):
        self.calls+=1
        return build_analytics([],query,[],None)
    def get_evaluation(self,module_key,source_id,source_table=None):
        if source_id!=1:return None
        return AdminEvaluationDetail(id='ev_evaluacion:1',source_table='ev_evaluacion',source_id=1,module_key='baya',fecha=date(2026,8,26),detalle={'observaciones':[{'numero_muestra':i,'diametro_mm':i+1} for i in range(60)]})
    def export_evaluations(self,query):
        yield 'source_id,fecha\r\n1,2026-08-26\r\n'

def setup(permission='*'):
    repository=Repository()
    app.dependency_overrides[get_admin_repository]=lambda:repository
    app.dependency_overrides[get_admin_user]=lambda:AuthUser(usuario_id=1,email='test@local',nombre='Test',rol='analista',permisos=[permission])
    return TestClient(app),repository

def test_analytics_requires_family_and_rejects_invalid_weight_interval():
    c,r=setup()
    try:
        assert c.get('/v1/admin/evaluaciones/analitica').status_code==422
        assert c.get('/v1/admin/evaluaciones/analitica?module_key=pesos&weight_min=4&weight_max=1').status_code==422
        assert r.calls==0
        assert c.get('/v1/admin/evaluaciones/analitica?module_key=pesos').status_code==200
    finally:app.dependency_overrides.clear()

def test_new_read_surfaces_enforce_permission():
    c,r=setup('admin:panel:leer')
    try:
        for path in ['analitica/tendencia?module_key=pesos','analitica?module_key=pesos','exportar','ficha/baya/1','observaciones/baya/1']:
            assert c.get('/v1/admin/evaluaciones/'+path).status_code==403
        assert r.calls==0
    finally:app.dependency_overrides.clear()

def test_card_and_observations_are_separate_and_paged():
    c,r=setup()
    try:
        card=c.get('/v1/admin/evaluaciones/ficha/baya/1').json()
        assert 'observaciones' not in card['detalle'] and card['detalle']['total_observaciones']==60
        page=c.get('/v1/admin/evaluaciones/observaciones/baya/1?page=2').json()
        assert page['total']==60 and len(page['items'])==25 and page['items'][0]['numero_muestra']==25
        assert c.get('/v1/admin/evaluaciones/ficha/baya/2').status_code==404
        assert c.get('/v1/admin/evaluaciones/observaciones/baya/1?page=0').status_code==422
    finally:app.dependency_overrides.clear()


def test_trend_requires_explicit_context_before_repository_access():
    client, repository = setup()
    try:
        assert client.get('/v1/admin/evaluaciones/analitica/tendencia?module_key=flores').status_code == 422
        assert repository.calls == 0
    finally:
        app.dependency_overrides.clear()
