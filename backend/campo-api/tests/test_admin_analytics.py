from datetime import date
import pytest
from aquanqa_campo_api.modules.admin.analytics import AnalyticsQuery, aggregate, build_analytics, build_stage_analysis, describe

def row(detail, day=date(2026,8,26), lot=1, id=1):
    return dict(source_id=id,fecha=day,lote_id=lot,fundo='F',modulo='M',lote='L',detalle=detail)

def calc(module, rows, **kwargs):
    return aggregate(rows,AnalyticsQuery(module_key=module,**kwargs),'all','Consulta')

@pytest.mark.parametrize('compact', [False, True])
@pytest.mark.parametrize('history', [False, True])
def test_stage_grouping_sets_preserve_denominators_lots_and_empty_days(compact, history):
    day = date(2026,8,24)
    rows = [row(dict(e1=0,e2=2,e3=4,e4=6,e5=8),day),row(dict(e1=99),day),
            row(dict(e1=0,e2=0,e3=0,e4=0,e5=0),day,lot=2)]
    groups = []
    for kind,lot,subset in [(3,None,rows),(1,1,rows[:2]),(1,2,rows[2:]),(2,None,rows)]:
        b=aggregate(subset,AnalyticsQuery(module_key='estadios'),'x','x')
        groups.append(dict(bucket_kind=kind,lote_id=lot,fecha=day if kind==2 else None,
            fundo='F',modulo='M',lote='L',evaluations=b.evaluations,complete=b.complete,
            **{f'e{i}':b.categories.get(f'E{i}') for i in range(1,6)}))
    q=AnalyticsQuery(module_key='estadios',snapshot=False,desde=day,hasta=date(2026,8,26),
                     include_trend=history,series_only=compact)
    assert build_stage_analysis(groups,q,['registro_access'],'registro_access').model_dump() == build_analytics(rows,q,['registro_access'],'registro_access').model_dump()

@pytest.mark.parametrize('family', ['estadios', 'flores', 'baya', 'pesos', 'brotes', 'ramas'])
def test_compact_period_series_preserves_chart_values_and_full_aggregates(family):
    samples = [dict(numero_muestra=1, nro_rama=1, diametro=5, diametro_mm=5, peso_g=0),
               dict(numero_muestra=2, nro_rama=2, diametro=8, diametro_mm=8, peso_g=4),
               dict(numero_muestra=2, nro_rama=2, diametro=99, diametro_mm=99, peso_g=9),
               dict(numero_muestra=3, nro_rama=3, diametro=3, diametro_mm=3, peso_g=2)]
    detail = dict(e1=0,e2=2,e3=4,e4=6,e5=8,n_flores=0,cuajo=5,brotes=0,
                  ramas_menor5=5,ramas_mayor5=10,observaciones=samples,mediciones=samples)
    rows = [row(detail, date(2026,8,24)), row({}, date(2026,8,26))]
    query = AnalyticsQuery(module_key=family, snapshot=False, hasta=date(2026,8,26))
    full = build_analytics(rows, query, ['registro_access'], 'registro_access')
    compact = build_analytics(rows, query.model_copy(update={'series_only':True}), ['registro_access'], 'registro_access')
    assert compact.model_dump(exclude={'trend'}) == full.model_dump(exclude={'trend'})
    assert len(compact.trend) == len(full.trend) == 3
    for expected, actual in zip(full.trend, compact.trend):
        for field in ('key','label','evaluations','observations','excluded','categories'):
            assert getattr(actual, field) == getattr(expected, field)
        for field in ('n','median','q1','q3'):
            assert getattr(actual.distribution, field) == getattr(expected.distribution, field)
        assert 'scatter' not in actual.model_dump()

def test_stages_only_complete_counts_and_zero_is_observed():
    result=calc('estadios',[row(dict(e1=10,e2=0,e3=0,e4=0,e5=90)),row(dict(e1=999,e5=1))])
    assert result.complete==1 and result.excluded==1
    assert result.categories==dict(E1=10,E2=0,E3=0,E4=0,E5=90)

def test_flowers_do_not_sum_categories_and_null_is_not_zero():
    r=calc('flores',[row(dict(n_flores=0,cuajo=10)),row(dict(n_flores=None,cuajo=2))])
    assert r.distribution.n==1 and r.distribution.mean==0
    assert r.categories=={} and r.availability['cuajo']==2

def test_weight_pairs_and_sample_weighted_average():
    rows=[row({'observaciones':[{'peso_g':1,'diametro_mm':10}]}),row({'observaciones':[{'peso_g':4,'diametro_mm':20},{'peso_g':7}]})]
    r=calc('pesos',rows,weight_min=3,weight_max=6)
    assert r.distribution.mean==4 and r.complete==2 and r.observations==3 and r.within_weight==1

def test_declared_branches_are_separate_from_diameters():
    r=calc('ramas',[row(dict(ramas_menor5=100,ramas_mayor5=200,mediciones=[dict(diametro=5),dict(diametro=9,sospechoso=True)]))])
    assert r.categories=={'< 5 mm':100,'> 5 mm':200}
    assert r.sample_categories=={'= 5 mm':1} and r.distribution.n==1 and r.excluded==1

def test_state_only_sample_is_preserved():
    r=calc('baya',[row({'observaciones':[{'estado_codigo':'CAIDO'},{'diametro_mm':10}]})])
    assert r.observations==2 and r.distribution.n==1 and r.categories=={'CAIDO':1,'Sin estado':1}

def test_missing_floor_not_fabricated_from_des_fields():
    r=calc('brotes',[row(dict(brotes=0,des1_origen='5'))])
    assert r.categories=={'Sin piso':0} and 'piso' not in r.availability

def test_snapshot_and_missing_days():
    q=AnalyticsQuery(module_key='flores',hasta=date(2026,8,26))
    r=build_analytics([row({'n_flores':2},date(2026,8,24)),row({'n_flores':8})],q,['registro_access'],'registro_access')
    assert r.summary.evaluations==1 and len(r.trend)==3
    assert r.trend[1].distribution.median is None

def test_scatter_is_bounded_reproducible_without_truncating_statistics():
    rows=[row({'observaciones':[{'peso_g':i+1,'diametro_mm':1} for i in range(2101)]})]
    a,b=calc('pesos',rows),calc('pesos',rows)
    assert len(a.scatter)==2000 and a.scatter_total==2101 and a.distribution.n==2101
    assert a.scatter==b.scatter

def test_empty_and_singleton_distributions():
    assert describe([]).median is None and describe([1]).cv is None
    assert describe([1,3]).median==2

def test_conflicting_ordinal_does_not_silently_keep_first_measurement():
    r=calc('ramas',[row({'mediciones':[{'nro_rama':1,'diametro':3,'numero_medicion':1},{'nro_rama':1,'diametro':8,'numero_medicion':2}]})])
    assert r.excluded==2 and r.distribution.n==0
