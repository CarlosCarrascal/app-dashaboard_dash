import { describe, it, expect } from 'vitest';
import { trendChart, type FieldAnalytics } from './field-analytics';

describe('Stage evolution calendar', () => {
  it('joins observed dates without empty slots and preserves readable hover', () => {
    const result = trendChart({
      module_key: 'estadios', trend_desde: '2026-08-01', hasta: '2026-08-07',
      trend: [
        { label: '2026-08-01', categories: { E1: 20, E2: 80 } },
        { label: '2026-08-02', categories: {} },
        { label: '2026-08-06', categories: { E1: 50, E2: 50 } },
        { label: '2026-08-07', categories: { E1: 0, E2: 0 } },
      ],
    } as FieldAnalytics);
    expect(result.xAxis).toMatchObject({ type: 'category', data: ['2026-08-01', '2026-08-06'] });
    const series = result.series as { data: (number | null)[]; showSymbol: boolean; connectNulls: boolean }[];
    expect(series.every((s) => !s.showSymbol && !s.connectNulls)).toBe(true);
    expect(series[0].data).toEqual([20, 50]);
    expect(series.every((s) => s.data.length === 2 && s.data.every((v) => v !== null))).toBe(true);
    const tooltip = result.tooltip as { formatter: (params: unknown) => string };
    const text = tooltip.formatter([{ name: '2026-08-03', value: 9.395579, seriesName: 'E1', marker: '' }]);
    expect(text).toContain('ago');
    expect(text).toMatch(/9[.,]4 %/);
    expect(text).not.toContain('00:00');
    expect(tooltip.formatter([{ name: '2026-08-02', value: null }])).toBe('');
  });
});
