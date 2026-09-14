import { computed } from '@angular/core';
import type { EvaluationWorkspace } from '../evaluation-workspace.service';
import { Bucket, histogramChart, primaryChart, scatterChart, trendChart } from '../field-analytics';
type Host = Pick<
  EvaluationWorkspace,
  | 'analytics'
  | 'focusedLot'
  | 'metric'
  | 'chartMode'
  | 'contextData'
  | 'activeFamily'
  | 'percentage'
  | 'detailColumnLabel'
>;
/** Feature-specific controller. The host coordinates navigation and refresh after mutations. */
export class EvaluationAnalysis {
  constructor(private readonly getHost: () => Host) {}
  private get host(): Host {
    return this.getHost();
  }

  readonly sampleEntries = computed(() =>
    Object.entries(this.context()?.sample_categories ?? {}).map(([label, n]) => ({ label, n })),
  );

  readonly context = computed(
    () =>
      this.host.analytics()?.lots.find((l) => l.key === this.host.focusedLot()) ??
      this.host.analytics()?.summary ??
      null,
  );

  private readonly primaryData = computed(
    () => {
      const data = this.host.analytics();
      return data
        ? {
            module_key: data.module_key,
            lots: data.lots,
            states: data.states,
            summary: data.summary,
          }
        : null;
    },
    {
      equal: (previous, next) =>
        previous === next ||
        Boolean(
          previous &&
          next &&
          previous.module_key === next.module_key &&
          previous.lots === next.lots &&
          previous.states === next.states &&
          previous.summary === next.summary,
        ),
    },
  );

  readonly mainChart = computed(() => {
    const data = this.primaryData();
    return data ? primaryChart(data, this.host.metric(), this.host.chartMode()) : {};
  });

  readonly histogram = computed(() => (this.context() ? histogramChart(this.context()!) : {}));

  readonly evolution = computed(() =>
    this.host.contextData()
      ? trendChart(this.host.contextData()!)
      : this.host.analytics()
        ? trendChart(this.host.analytics()!)
        : {},
  );

  readonly flowerScatter = computed(() =>
    this.context() ? scatterChart(this.context()!, 'Flores', 'Cuajos') : {},
  );

  readonly metricOptions = [
    { key: 'n_flores', label: 'Flores' },
    { key: 'cuajo', label: 'Cuajos' },
    { key: 'yemas_por_abrir', label: 'Yema productiva' },
    { key: 'yemas_abiertas', label: 'Yema abierta' },
    { key: 'yemas_muertas', label: 'Muertas · nombre de origen' },
    { key: 'brotes_tiernos', label: 'Brotes tiernos' },
  ];

  readonly chartTitle = computed(
    () =>
      ({
        '': 'Análisis',
        estadios: 'Composición por lote',
        flores: 'Variación de conteos por lote',
        baya: 'Distribución del diámetro',
        pesos: 'Relación entre diámetro y peso',
        brotes: 'Brotes por lote y piso',
        ramas:
          this.host.chartMode() === 'conteos'
            ? 'Conteos declarados por lote'
            : 'Diámetros de ramas medidas',
      })[this.host.activeFamily()] ?? 'Análisis',
  );

  readonly unit = computed(() =>
    this.host.activeFamily() === 'pesos'
      ? 'g'
      : ['baya', 'ramas'].includes(this.host.activeFamily())
        ? 'mm'
        : 'por evaluación',
  );

  categoryEntries(bucket: Bucket) {
    return Object.entries(bucket.categories).map(([label, value]) => ({
      label,
      value,
      percent: this.host.percentage(
        value,
        Object.values(bucket.categories).reduce((a, b) => a + b, 0),
      ),
    }));
  }

  stagePercent(c: Bucket) {
    return this.host.percentage(
      c.categories['E5'] || 0,
      Object.values(c.categories).reduce((a, b) => a + b, 0),
    );
  }

  categoryTotal(c: Bucket) {
    return Object.values(c.categories).reduce((a, b) => a + b, 0);
  }

  availabilityEntries(c: Bucket) {
    const sample = ['baya', 'pesos', 'ramas'].includes(this.host.activeFamily());
    return Object.entries(c.availability)
      .filter(([k]) => !k.startsWith('BROTE'))
      .map(([key, n]) => ({
        label:
          (
            {
              diametro: 'Con diámetro',
              estado: 'Con estado',
              peso: 'Con peso',
              piso: 'Con piso',
            } as Record<string, string>
          )[key] ?? this.host.detailColumnLabel(key),
        n,
        percent: this.host.percentage(n, sample ? c.observations : c.evaluations),
      }));
  }
}
