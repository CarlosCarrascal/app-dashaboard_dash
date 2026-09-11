"""Analítica de lectura: cada distribución conserva su unidad y denominador."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from math import isfinite
from statistics import mean, stdev
from typing import Any, Literal

from pydantic import BaseModel, Field
from .schemas import AdminEvaluationQuery
from ..evaluaciones.schemas import ModuleKey


class AnalyticsQuery(AdminEvaluationQuery):
    snapshot_series: bool = False
    series_only: bool = False
    snapshot: bool = True
    include_trend: bool = True
    metric: Literal['n_flores','cuajo','yemas_abiertas','yemas_por_abrir','yemas_muertas','brotes_tiernos'] = 'n_flores'
    weight_min: float | None = Field(default=None, ge=0)
    weight_max: float | None = Field(default=None, ge=0)


class Distribution(BaseModel):
    n: int = 0
    mean: float | None = None
    median: float | None = None
    p10: float | None = None
    q1: float | None = None
    q3: float | None = None
    p90: float | None = None
    cv: float | None = None
    histogram: list[list[float]] = Field(default_factory=list)


class ObservationPage(BaseModel):
    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int


class AnalyticsBucket(BaseModel):
    key: str
    label: str
    lote_id: int | None = None
    evaluations: int
    observations: int
    complete: int
    excluded: int
    categories: dict[str, float]
    availability: dict[str, int]
    distribution: Distribution
    diameter: Distribution
    scatter: list[list[float | str]]
    scatter_total: int
    within_weight: int | None = None
    sample_categories: dict[str, int] = Field(default_factory=dict)


class EvaluationAnalytics(BaseModel):
    module_key: ModuleKey
    desde: date | None
    hasta: date | None
    trend_desde: date | None
    snapshot: bool
    grano: str | None
    grains: list[str]
    summary: AnalyticsBucket
    lots: list[AnalyticsBucket]
    trend: list[AnalyticsBucket | SeriesPoint]
    states: list[AnalyticsBucket] = Field(default_factory=list)


class SeriesDistribution(BaseModel):
    n: int = 0
    median: float | None = None
    q1: float | None = None
    q3: float | None = None


class SeriesPoint(BaseModel):
    key: str
    label: str
    evaluations: int
    observations: int
    excluded: int
    categories: dict[str, float] = Field(default_factory=dict)
    distribution: SeriesDistribution = Field(default_factory=SeriesDistribution)


def build_series(groups: list[dict], query: AnalyticsQuery) -> list[SeriesPoint]:
    if not groups:
        return []
    by_day = {row['fecha']: row for row in groups}
    day, end = min(by_day), query.hasta or max(by_day)
    points = []
    while day <= end:
        row = by_day.get(day, {})
        quantiles = row.get('quantiles') or [None, None, None]
        points.append(SeriesPoint(key=str(day), label=str(day), evaluations=row.get('evaluations', 0),
            observations=row.get('observations', 0), excluded=row.get('excluded', 0),
            distribution=SeriesDistribution(n=row.get('n', 0), q1=quantiles[0], median=quantiles[1], q3=quantiles[2])))
        day += timedelta(days=1)
    return points


class EvaluationTrend(BaseModel):
    module_key: ModuleKey
    desde: date
    hasta: date
    grano: str
    trend: list[AnalyticsBucket | SeriesPoint]


def build_trend(rows: list[dict], query: AnalyticsQuery) -> list[AnalyticsBucket]:
    dates = defaultdict(list)
    for row in rows:
        dates[str(row['fecha'])].append(row)
    if rows:
        day = min(r['fecha'] for r in rows)
        end = query.hasta or max(r['fecha'] for r in rows)
        while day <= end:
            dates.setdefault(str(day), [])
            day += timedelta(days=1)
    return [aggregate(group, query, day, day) for day, group in sorted(dates.items())]


def build_stage_trend(groups: list[dict], query: AnalyticsQuery) -> list[AnalyticsBucket]:
    if not groups:
        return []
    by_day = {row['fecha']: row for row in groups}
    day, end = min(by_day), query.hasta or max(by_day)
    result = []
    while day <= end:
        bucket = aggregate([], query, str(day), str(day))
        if row := by_day.get(day):
            bucket.evaluations = row['evaluations']
            bucket.complete = row['complete']
            bucket.excluded = row['evaluations'] - row['complete']
            bucket.categories = {f'E{i}': float(row[f'e{i}']) for i in range(1, 6)} if row['complete'] else {}
        result.append(bucket)
        day += timedelta(days=1)
    return result


def build_stage_analysis(groups: list[dict], query: AnalyticsQuery, grains: list[str], grano: str | None) -> EvaluationAnalytics:
    """Build full-population stage charts from SQL grouping sets, without raw captures."""
    result = build_analytics([], query, grains, grano)
    dates = []
    for row in groups:
        kind = row['bucket_kind']
        if kind == 2:
            dates.append(row)
            continue
        lot = row['lote_id'] if kind == 1 else None
        label = ' · '.join(str(row.get(k) or '—') for k in ('fundo','modulo','lote')) if kind == 1 else 'Consulta completa'
        bucket = aggregate([], query, str(lot) if kind == 1 else 'all', label, lot)
        bucket.evaluations = row['evaluations']
        bucket.complete = row['complete']
        bucket.excluded = row['evaluations'] - row['complete']
        bucket.categories = {f'E{i}':float(row[f'e{i}']) for i in range(1,6)} if row['complete'] else {}
        if kind == 1:
            result.lots.append(bucket)
        else:
            result.summary = bucket
    result.lots.sort(key=lambda bucket: bucket.lote_id)
    result.trend_desde = min((r['fecha'] for r in dates), default=None)
    if query.include_trend:
        result.trend = build_stage_trend(dates, query)
        if query.series_only:
            result.trend = [SeriesPoint(key=b.key,label=b.label,evaluations=b.evaluations,
                observations=b.observations,excluded=b.excluded,categories=b.categories) for b in result.trend]
    return result


def number(value: Any, positive: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if isfinite(value) and (value > 0 if positive else value >= 0) else None
    except (ValueError, TypeError):
        return None


def describe(values: list[float]) -> Distribution:
    if not values:
        return Distribution()
    values = sorted(values)
    def percentile(p: float) -> float:
        index = (len(values) - 1) * p
        lo = int(index)
        return values[lo] + (values[min(lo + 1, len(values) - 1)] - values[lo]) * (index - lo)
    average = mean(values)
    low, high = values[0], values[-1]
    width = (high - low) / 12 if high > low else 1
    bins = [0] * (12 if high > low else 1)
    for value in values:
        bins[min(int((value - low) / width), len(bins) - 1)] += 1
    return Distribution(n=len(values), mean=average, median=percentile(.5), p10=percentile(.1),
        q1=percentile(.25), q3=percentile(.75), p90=percentile(.9),
        cv=stdev(values) / average * 100 if len(values) > 1 and average else None,
        histogram=[[low + i * width, low + (i + 1) * width, n] for i, n in enumerate(bins)])


def aggregate(rows: list[dict], query: AnalyticsQuery, key: str, label: str, lote_id=None, *, series_only=False) -> AnalyticsBucket | SeriesPoint:
    values, diameters, points = [], [], []
    categories, availability, sample_categories = Counter(), Counter(), Counter()
    complete = observations = excluded = 0
    within = 0 if query.weight_min is not None or query.weight_max is not None else None
    for row in rows:
        data = row['detalle'] or {}
        family = query.module_key
        if family == 'estadios':
            stages = [number(data.get(f'e{i}')) for i in range(1, 6)]
            if all(v is not None for v in stages):
                complete += 1
                for i, value in enumerate(stages):
                    categories[f'E{i+1}'] += value
            else:
                excluded += 1
        elif family == 'flores':
            for field in ('n_flores', 'cuajo', 'yemas_abiertas', 'yemas_por_abrir', 'yemas_muertas', 'brotes_tiernos'):
                value = number(data.get(field))
                if value is not None:
                    availability[field] += 1
                    if field == query.metric:
                        values.append(value)
                        complete += 1
            x, y = number(data.get('n_flores')), number(data.get('cuajo'))
            if not series_only and x is not None and y is not None:
                points.append([x, y, str(row['source_id'])])
        elif family == 'brotes':
            value = number(data.get('brotes'))
            piso = data.get('piso') or 'Sin piso'
            if data.get('piso'):
                availability['piso'] += 1
            if value is not None:
                complete += 1
                values.append(value)
                categories[piso] += value
                availability[piso] += 1
        else:
            if family == 'ramas':
                small, large = number(data.get('ramas_menor5')), number(data.get('ramas_mayor5'))
                if small is not None and large is not None:
                    complete += 1
                    categories['< 5 mm'] += small
                    categories['> 5 mm'] += large
                samples = data.get('mediciones') or []
            else:
                samples = data.get('observaciones') or []
            ordinal_field = 'nro_rama' if family == 'ramas' else 'numero_muestra'
            repeated = Counter(s.get(ordinal_field) for s in samples if s.get(ordinal_field) is not None)
            for sample in samples:
                if query.estado and sample.get('estado_codigo') != query.estado:
                    continue
                observations += 1
                if sample.get('sospechoso') or repeated.get(sample.get(ordinal_field), 0) > 1 or (sample.get('numero_medicion') or 1) > 1:
                    excluded += 1
                    continue
                diameter = number(sample.get('diametro' if family == 'ramas' else 'diametro_mm'), True)
                weight = number(sample.get('peso_g'), True)
                if diameter is not None:
                    diameters.append(diameter)
                    availability['diametro'] += 1
                    if family == 'ramas':
                        sample_categories['< 5 mm' if diameter < 5 else ('= 5 mm' if diameter == 5 else '> 5 mm')] += 1
                if family == 'pesos':
                    if weight is not None:
                        values.append(weight)
                        availability['peso'] += 1
                        if within is not None and (query.weight_min is None or weight >= query.weight_min) and (query.weight_max is None or weight <= query.weight_max):
                            within += 1
                    if weight is not None and diameter is not None:
                        complete += 1
                        if not series_only:
                            points.append([diameter, weight, str(row['source_id'])])
                else:
                    if diameter is not None:
                        values.append(diameter)
                    if family == 'baya':
                        state = sample.get('estado_codigo') or 'Sin estado'
                        categories[state] += 1
                        if sample.get('estado_codigo'):
                            availability['estado'] += 1
                        complete += 1
    if series_only:
        ordered = sorted(values)
        def quantile(p: float) -> float | None:
            if not ordered:
                return None
            index = (len(ordered) - 1) * p
            low = int(index)
            return ordered[low] + (ordered[min(low + 1, len(ordered) - 1)] - ordered[low]) * (index - low)
        return SeriesPoint(key=key, label=label, evaluations=len(rows), observations=observations,
            excluded=excluded, categories=dict(categories), distribution=SeriesDistribution(
                n=len(ordered), median=quantile(.5), q1=quantile(.25), q3=quantile(.75)))
    # A deterministic, evenly spaced selection across ordered observations. Aggregates use all values.
    total_points = len(points)
    if total_points > 2000:
        points = [points[i * total_points // 2000] for i in range(2000)]
    diameter_stats = describe(diameters)
    value_stats = diameter_stats if query.module_key in {'baya', 'ramas'} else describe(values)
    return AnalyticsBucket(key=key, label=label, lote_id=lote_id, evaluations=len(rows),
        observations=observations, complete=complete, excluded=excluded, categories=dict(categories),
        availability=dict(availability), distribution=value_stats, diameter=diameter_stats,
        scatter=points, scatter_total=total_points, within_weight=within, sample_categories=dict(sample_categories))


def build_analytics(rows: list[dict], query: AnalyticsQuery, grains: list[str], grano: str | None) -> EvaluationAnalytics:
    end = query.hasta or max((r['fecha'] for r in rows), default=None)
    selected = [r for r in rows if not query.snapshot or r['fecha'] == end]
    lots, dates = defaultdict(list), defaultdict(list)
    for row in selected:
        lots[row['lote_id']].append(row)
    if query.include_trend:
        for row in rows:
            dates[str(row['fecha'])].append(row)
    if rows and query.include_trend:
        day = min(r['fecha'] for r in rows)
        while day <= end:
            dates.setdefault(str(day), [])
            day += timedelta(days=1)
    state_groups = defaultdict(list)
    if query.module_key == 'baya':
        for row in selected:
            by_state = defaultdict(list)
            for sample in row['detalle'].get('observaciones') or []:
                if not query.estado or sample.get('estado_codigo') == query.estado:
                    by_state[sample.get('estado_codigo') or 'Sin estado'].append(sample)
            for state, samples in by_state.items():
                state_groups[state].append({**row, 'detalle': {**row['detalle'], 'observaciones': samples}})
    return EvaluationAnalytics(module_key=query.module_key, desde=end if query.snapshot else query.desde,
        hasta=end, trend_desde=min((r['fecha'] for r in rows), default=None), snapshot=query.snapshot,
        grano=grano, grains=grains, summary=aggregate(selected, query, 'all', 'Consulta completa'),
        lots=[aggregate(group, query, str(lot), ' · '.join(str(group[0].get(k) or '—') for k in ('fundo','modulo','lote')), lot)
              for lot, group in sorted(lots.items())],
        trend=[aggregate(group, query, day, day, series_only=query.series_only) for day, group in sorted(dates.items())],
        states=[aggregate(group, query, state, state) for state, group in sorted(state_groups.items())])
