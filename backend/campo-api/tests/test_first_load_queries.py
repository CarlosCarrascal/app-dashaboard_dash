from contextlib import contextmanager
from datetime import date
from aquanqa_campo_api.infrastructure.postgres.admin_repository import PostgresAdminRepository
from aquanqa_campo_api.modules.admin.schemas import AdminMasterQuery
from aquanqa_campo_api.modules.admin.analytics import AnalyticsQuery, build_analytics

class Database:
    def __init__(self, rows, total=3):
        self.rows, self.total, self.calls = rows, total, []
    @contextmanager
    def read(self):
        yield self
    @contextmanager
    def cursor(self):
        yield self
    def execute(self, sql, params):
        self.calls.append((sql, params))
    def fetchall(self):
        return [dict(row) for row in self.rows]
    def fetchone(self):
        return {"total": self.total}

def test_first_master_page_counts_and_reads_in_one_statement():
    db = Database([{"empresa_id": 2, "nombre": "A", "_filtered_total": 3}])
    result = PostgresAdminRepository(db, unrestricted=True).list_master("empresas", AdminMasterQuery())
    assert len(db.calls) == 1
    assert result.meta.total == 3
    assert result.items == [{"empresa_id": 2, "nombre": "A"}]

def test_out_of_range_page_preserves_total_without_fake_rows():
    db = Database([])
    result = PostgresAdminRepository(db, unrestricted=True).list_master("empresas", AdminMasterQuery(page=99))
    assert len(db.calls) == 2
    assert result.items == []
    assert result.meta.total == 3

def test_snapshot_does_not_compute_discarded_temporal_buckets(monkeypatch):
    import aquanqa_campo_api.modules.admin.analytics as module
    original = module.aggregate
    keys = []
    def tracked(rows, query, key, label, lote_id=None):
        keys.append(key)
        return original(rows, query, key, label, lote_id)
    monkeypatch.setattr(module, "aggregate", tracked)
    rows = [{"fecha": date(2026, 8, 26), "lote_id": 1, "source_id": 1, "detalle": {"e1": 0, "e2": 2, "e3": 3, "e4": 4, "e5": 5}}]
    result = build_analytics(rows, AnalyticsQuery(module_key="estadios", include_trend=False), [], None)
    assert result.trend == []
    assert keys == ["all", "1"]
    assert result.summary.categories["E1"] == 0


def test_empty_first_page_needs_no_second_count():
    db = Database([], total=0)
    result = PostgresAdminRepository(db, unrestricted=True).list_users(AdminMasterQuery())
    assert len(db.calls) == 1
    assert result.meta.total == 0
    assert result.items == []


def test_trend_projection_matches_full_analysis_including_missing_days():
    from aquanqa_campo_api.modules.admin.analytics import build_trend
    rows = [
        {"fecha": date(2026, 8, day), "lote_id": 1, "source_id": day, "detalle": {"n_flores": value, "cuajo": 0}}
        for day, value in [(20, 0), (22, 12)]
    ]
    query = AnalyticsQuery(module_key="flores", snapshot=False, desde=date(2026,8,20), hasta=date(2026,8,22))
    full = build_analytics(rows, query, [], None)
    assert build_trend(rows, query) == full.trend
    assert full.trend[1].evaluations == 0


def test_daily_stage_aggregates_preserve_denominators_zeros_and_missing_days():
    from aquanqa_campo_api.modules.admin.analytics import build_trend, build_stage_trend
    query = AnalyticsQuery(module_key='estadios', desde=date(2026,8,20), hasta=date(2026,8,23), grano='registro_access')
    details = [
        (20, dict(e1=0, e2=0, e3=0, e4=0, e5=0)),
        (20, dict(e1=100, e2=None, e3=1, e4=1, e5=1)),
        (22, dict(e1=1, e2=2, e3=3, e4=4, e5=5)),
        (22, dict(e1=-1, e2=10, e3=10, e4=10, e5=10)),
    ]
    rows = [{'fecha':date(2026,8,day),'detalle':detail} for day,detail in details]
    groups = [dict(fecha=date(2026,8,20), evaluations=2, complete=1, e1=0,e2=0,e3=0,e4=0,e5=0),
              dict(fecha=date(2026,8,22), evaluations=2, complete=1, e1=1,e2=2,e3=3,e4=4,e5=5)]
    assert build_stage_trend(groups,query) == build_trend(rows,query)
    assert build_stage_trend([],query) == []
    assert build_stage_trend([dict(fecha=date(2026,8,20),evaluations=1,complete=0)],query)[0].categories == {}


def test_stage_trend_aggregates_in_one_scoped_read():
    db = Database([])
    result = PostgresAdminRepository(db, usuario_id=17, unrestricted=False).evaluation_trend(
        AnalyticsQuery(module_key='estadios', desde=date(2026,8,20), hasta=date(2026,8,23), grano='registro_access', lote_id=42))
    assert len(db.calls) == 1
    sql, params = db.calls[0]
    assert 'stage_validity' in sql
    assert 42 in params and 17 in params
    assert result.trend == []
