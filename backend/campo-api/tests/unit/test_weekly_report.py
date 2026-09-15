from contextlib import contextmanager
from datetime import date
from unittest.mock import Mock
import pytest
from pydantic import ValidationError
from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.modules.admin.weekly_report import WeeklyReportQuery

class Database:
    def __init__(self, empty=False): self.calls=[]; self.empty=empty
    @contextmanager
    def read(self): yield self
    @contextmanager
    def cursor(self): yield self
    def execute(self,sql,params): self.calls.append((sql,params))
    def fetchall(self):
        if self.empty:return []
        if len(self.calls)==1:return [{'grano':'captura','fecha':date(2026,9,14)}]
        return [dict(week=date(2026,9,14),fundo_id=2,fundo='F2',modulo_id=3,modulo='M03',evaluations=3,available=2,total=10,mean=5)]

def test_report_scopes_every_query_and_averages_observations_not_weekly_means():
    db=Database();repo=PostgresAdminRepository(db)
    repo._append_scope=Mock(side_effect=lambda c,p,k:(c.append('empresa_id = %s'),p.append(9)))
    result=repo.weekly_report(WeeklyReportQuery(metric='cuajo',weeks=8,fundo_id=2))
    assert result.grano=='captura' and result.hasta==date(2026,9,14)
    assert result.desde==date(2026,7,27)
    assert result.points[0].mean==5 and result.points[0].available==2
    for sql,params in db.calls:
        assert 'empresa_id = %s' in sql and 9 in params and 2 in params
    sql,params=db.calls[1]
    assert 'count(value) available,sum(value) total,avg(value) mean' in sql
    assert params[0]=='cuajo'
    assert 'COALESCE' not in sql.split('measured AS (')[1]

def test_report_empty_keeps_absent_dates_and_no_fake_points():
    result=PostgresAdminRepository(Database(True)).weekly_report(WeeklyReportQuery())
    assert result.points==[] and result.hasta is None and result.grano is None

def test_report_rejects_unsupported_metrics_and_unbounded_weeks():
    for value in [{'metric':'births'},{'weeks':1000},{'module_key':'pesos'}]:
        with pytest.raises(ValidationError):WeeklyReportQuery(**value)
