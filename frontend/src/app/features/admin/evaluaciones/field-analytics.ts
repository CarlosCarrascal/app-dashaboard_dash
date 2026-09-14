import type { EChartsOption } from 'echarts';

export interface Distribution {
  n: number;
  mean: number | null;
  median: number | null;
  p10: number | null;
  q1: number | null;
  q3: number | null;
  p90: number | null;
  cv: number | null;
  histogram: number[][];
}
export interface Bucket {
  key: string;
  label: string;
  lote_id: number | null;
  evaluations: number;
  observations: number;
  complete: number;
  excluded: number;
  categories: Record<string, number>;
  availability: Record<string, number>;
  distribution: Distribution;
  diameter: Distribution;
  scatter: (number | string)[][];
  scatter_total: number;
  within_weight: number | null;
  sample_categories: Record<string, number>;
}
export interface FieldAnalytics {
  module_key: string;
  desde: string | null;
  hasta: string | null;
  trend_desde: string | null;
  snapshot: boolean;
  grano: string | null;
  grains: string[];
  summary: Bucket;
  lots: Bucket[];
  trend: Array<
    Pick<Bucket, 'key' | 'label' | 'categories'> & {
      distribution: Pick<Distribution, 'n' | 'median' | 'q1' | 'q3'>;
    }
  >;
  states: Bucket[];
}
export const stageNames = [
  'E1 · Verde 100 %',
  'E2 · Rosado 25 %',
  'E3 · Mitad rosado',
  'E4 · Rosado >75 %',
  'E5 · Azul 100 %',
];
export const palette = ['#145b45', '#23946f', '#89c16c', '#e9aa48', '#57759a'];
const base: EChartsOption = {
  color: palette,
  tooltip: { trigger: 'item', confine: true, renderMode: 'richText' },
  grid: { top: 28, right: 24, bottom: 60, left: 12, containLabel: true },
};
const pct = (n: number, total: number) => (total ? (n / total) * 100 : 0);
export type PrimaryChartData = Pick<FieldAnalytics, 'module_key' | 'lots' | 'states' | 'summary'>;
export function primaryChart(data: PrimaryChartData, metric: string, mode: string): EChartsOption {
  const lots = data.module_key === 'baya' && mode === 'estados' ? data.states : data.lots;
  const names = lots.map((x) =>
    x.label.includes(' · ') ? x.label.split(' · ').reverse().join(' · ') : x.label,
  );
  const smallScreen = [
    {
      query: { maxWidth: 500 },
      option: {
        grid: { left: 4, right: 24, top: 25, bottom: 65, containLabel: true },
        yAxis: { axisLabel: { width: 52, formatter: (name: string) => name.split(' · ')[0] } },
      },
    },
  ];
  const zoom =
    lots.length > 12
      ? [
          {
            type: 'slider' as const,
            yAxisIndex: 0,
            start: 0,
            end: Math.min(100, 1200 / lots.length),
            right: 0,
          },
        ]
      : [];
  if (data.module_key === 'estadios' || data.module_key === 'brotes') {
    const keys =
      data.module_key === 'estadios'
        ? ['E1', 'E2', 'E3', 'E4', 'E5']
        : [...new Set(lots.flatMap((l) => Object.keys(l.categories)))].sort();
    const points = lots.flatMap((l, y) => {
      const total = Object.values(l.categories).reduce((a, b) => a + b, 0);
      return keys.flatMap((k, x) => {
        const n = l.categories[k];
        if (n === undefined || (data.module_key === 'estadios' && !total)) return [];
        return [
          {
            value: [
              x,
              y,
              data.module_key === 'estadios' ? pct(n, total) : n / (l.availability[k] || 1),
            ],
            lot: l.key,
          },
        ];
      });
    });
    return {
      ...base,
      grid: { left: 10, right: 30, top: 40, bottom: 70, containLabel: true },
      dataZoom: zoom,
      xAxis: {
        type: 'category',
        data: keys,
        position: 'top',
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'category',
        data: names,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { width: 130, overflow: 'truncate' },
      },
      visualMap: {
        min: 0,
        max: data.module_key === 'estadios' ? 100 : Math.max(1, ...points.map((p) => p.value[2])),
        orient: 'horizontal',
        left: 'center',
        bottom: 0,
        inRange: { color: ['#f0f8e9', '#b9ed82', '#23946f', '#145b45'] },
        text: data.module_key === 'estadios' ? ['100 %', '0 %'] : ['Más brotes', 'Menos brotes'],
      },
      series: [
        {
          type: 'heatmap',
          data: points,
          label: { show: true, formatter: (p) => Number((p.value as number[])[2]).toFixed(1) },
          itemStyle: { borderWidth: 4, borderColor: '#fff', borderRadius: 5 },
          emphasis: { itemStyle: { borderColor: '#e9aa48' } },
        },
      ],
      media: [
        {
          query: { maxWidth: 500 },
          option: {
            grid: { left: 4, right: 24, top: 25, bottom: 65, containLabel: true },
            yAxis: { axisLabel: { width: 52, formatter: (name: string) => name.split(' · ')[0] } },
            series: [{ label: { fontSize: 10 }, itemStyle: { borderWidth: 2 } }],
          },
        },
      ],
    };
  }
  if (data.module_key === 'pesos') return scatterChart(data.summary, 'Diámetro (mm)', 'Peso (g)');
  if (data.module_key === 'ramas' && mode === 'conteos')
    return {
      ...base,
      dataZoom: zoom,
      xAxis: { type: 'value', name: 'Ramas declaradas', nameLocation: 'middle', nameGap: 32 },
      media: smallScreen,
      yAxis: { type: 'category', data: names, inverse: true },
      series: ['< 5 mm', '> 5 mm'].map((k, i) => ({
        type: 'bar' as const,
        name: k,
        stack: 'total',
        itemStyle: { color: palette[i] },
        data: lots.map((l) => ({ value: l.categories[k] ?? null, lot: l.key })),
      })),
    };
  const unit = data.module_key === 'flores' ? 'Conteo por evaluación' : 'Diámetro (mm)';
  return {
    ...base,
    dataZoom: zoom,
    xAxis: { type: 'value', name: unit, nameLocation: 'middle', nameGap: 32 },
    media: smallScreen,
    yAxis: {
      type: 'category',
      data: names,
      inverse: true,
      axisLabel: { width: 120, overflow: 'truncate' },
    },
    series: [
      {
        type: 'boxplot',
        data: lots.map((l) => ({
          value: [
            l.distribution.p10,
            l.distribution.q1,
            l.distribution.median,
            l.distribution.q3,
            l.distribution.p90,
          ] as number[],
          lot: l.key,
        })),
        itemStyle: { color: '#e7f3df', borderColor: '#23946f' },
      },
    ],
  };
}
export function scatterChart(bucket: Bucket, x: string, y: string): EChartsOption {
  return {
    ...base,
    grid: { left: 48, right: 30, top: 38, bottom: 55, containLabel: true },
    xAxis: { type: 'value', name: x, nameLocation: 'middle', nameGap: 30 },
    yAxis: { type: 'value', name: y },
    series: [
      {
        type: 'scatter',
        symbolSize: 7,
        itemStyle: { color: '#23946f', opacity: 0.6 },
        data: bucket.scatter.map((p) => ({ value: p.slice(0, 2), name: 'record:' + String(p[2]) })),
      },
    ],
  };
}
export function histogramChart(bucket: Bucket): EChartsOption {
  return {
    ...base,
    grid: { left: 8, right: 8, top: 15, bottom: 28, containLabel: true },
    xAxis: {
      type: 'category',
      data: bucket.distribution.histogram.map((b) => b[0].toFixed(1)),
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: '#edf0ec' } } },
    series: [
      {
        type: 'bar',
        data: bucket.distribution.histogram.map((b) => b[2]),
        itemStyle: { color: '#23946f', borderRadius: [3, 3, 0, 0] },
        barCategoryGap: '5%',
      },
    ],
  };
}
export function trendChart(data: FieldAnalytics): EChartsOption {
  const series =
    data.module_key === 'estadios'
      ? ['E1', 'E2', 'E3', 'E4', 'E5'].map((k, i) => ({
          name: k,
          type: 'line' as const,
          stack: 'stages',
          areaStyle: { opacity: 0.8 },
          showSymbol: false,
          itemStyle: { color: palette[i] },
          data: data.trend.map((b) => {
            const sum = Object.values(b.categories).reduce((a, c) => a + c, 0);
            return sum ? pct(b.categories[k] || 0, sum) : null;
          }),
        }))
      : [
          {
            name: 'Mediana',
            type: 'line' as const,
            showSymbol: true,
            connectNulls: false,
            data: data.trend.map((b) => b.distribution.median),
            itemStyle: { color: '#145b45' },
          },
          {
            name: 'P25',
            type: 'line' as const,
            symbol: 'none',
            data: data.trend.map((b) => b.distribution.q1),
            lineStyle: { type: 'dashed' as const, color: '#89c16c' },
          },
          {
            name: 'P75',
            type: 'line' as const,
            symbol: 'none',
            data: data.trend.map((b) => b.distribution.q3),
            lineStyle: { type: 'dashed' as const, color: '#89c16c' },
          },
        ];
  return {
    ...base,
    tooltip: { trigger: 'axis', confine: true, renderMode: 'richText' },
    grid: { left: 10, right: 12, top: 15, bottom: 30, containLabel: true },
    xAxis: {
      type: 'category',
      data: data.trend.map((b) => b.label.slice(5)),
      axisLabel: { fontSize: 11 },
    },
    yAxis: { type: 'value', max: data.module_key === 'estadios' ? 100 : undefined },
    series,
  };
}
