from contextlib import contextmanager
from unittest.mock import Mock
from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.modules.admin.schemas import AdminEvaluationQuery
class Database:
    def __init__(self, rows): self.rows=rows; self.executed=[]
    @contextmanager
    def read(self): yield self
    @contextmanager
    def cursor(self): yield self
    def execute(self,sql,params): self.executed.append((sql,params))
    def fetchall(self): return self.rows

def test_counts_keep_scope_and_do_not_materialize_samples():
    db=Database([dict(module_key=None,overall=1,total=3,lotes=2,evaluadores=1,desde=None,hasta=None,ultima_captura=None),dict(module_key='estadios',overall=0,total=3)])
    repo=PostgresAdminRepository(db)
    repo._append_scope=Mock(side_effect=lambda conditions,params,columns:(conditions.append('empresa_id = %s'),params.append(7)))
    result=repo.evaluation_counts(AdminEvaluationQuery(fundo_id=2,grano='captura'))
    assert (result.total,result.lotes,result.evaluadores)==(3,2,1)
    sql,params=db.executed[0]
    assert 'jsonb_agg' not in sql and 'ev_fruto_observacion' not in sql
    assert 'GROUPING SETS' in sql and 'empresa_id = %s' in sql
    assert 7 in params and 2 in params and 'captura' in params
    assert result.por_modulo[0].total==3

def test_empty_counts_keep_zero_and_absent_date():
    db=Database([dict(module_key=None,overall=1,total=0,lotes=0,evaluadores=0,desde=None,hasta=None,ultima_captura=None)])
    result=PostgresAdminRepository(db).evaluation_counts(AdminEvaluationQuery())
    assert result.total==0 and result.por_modulo==[] and result.ultima_captura is None
