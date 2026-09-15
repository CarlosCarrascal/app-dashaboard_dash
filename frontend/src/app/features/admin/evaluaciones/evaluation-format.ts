import { HttpErrorResponse } from '@angular/common/http';
import type { AdminEvaluationDetail } from '../../../core/api/models';
export function formatMetric(value: number | null | undefined) {
  return value == null ? '—' : value.toLocaleString('es-PE', { maximumFractionDigits: 2 });
}

export function formatCell(value: unknown) {
  return typeof value === 'number' ? formatMetric(value) : value == null ? '—' : String(value);
}

export function percentage(n: number, d: number) {
  return d ? (n / d) * 100 : null;
}

export function grainLabel(value: string | null) {
  return (
    (
      {
        registro_access: 'Registro histórico',
        captura: 'Capturas de campo',
        grupo_historico_planta: 'Grupo histórico por planta',
        grupo_historico_hilera: 'Grupo histórico por hilera',
      } as Record<string, string>
    )[value ?? ''] ??
    value ??
    'Unidad no definida'
  );
}

export function formatDate(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat('es-PE', { dateStyle: 'medium', timeZone: 'America/Lima' }).format(
        new Date(value.length === 10 ? `${value}T12:00:00-05:00` : value),
      )
    : 'Sin datos';
}

export function formatCapture(value: string | null | undefined): string {
  return value
    ? new Intl.DateTimeFormat('es-PE', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'America/Lima',
      }).format(new Date(value))
    : 'Sin hora';
}

export function numberValue(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? number : 0;
}

export function messageFor(
  error: unknown,
  fallback = 'No se pudo consultar evaluaciones. Revisa la conexión con FastAPI.',
): string {
  if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
    return error.error.detail;
  }
  return fallback;
}

export function detailEntries(
  detail: AdminEvaluationDetail,
): Array<{ label: string; value: string }> {
  const data = detail.detalle ?? {};
  const labels: Record<string, string> = {
    e1: 'E1 · Verde 100 %',
    e2: 'E2 · Rosado 25 %',
    e3: 'E3 · Mitad rosado',
    e4: 'E4 · Rosado >75 %',
    e5: 'E5 · Azul 100 %',
    total: 'Total',
    total_origen: 'Total de origen',
    n_flores: 'Flores',
    cuajo: 'Cuajos',
    yemas_abiertas: 'Yemas abiertas',
    yemas_por_abrir: 'Yemas por abrir',
    yemas_muertas: 'Yemas muertas',
    brotes_tiernos: 'Brotes tiernos',
    brotes: 'Total de brotes',
    des1: 'Des1 · origen',
    des2: 'Des2 · origen',
    des3: 'Des3 · origen',
    ramas_menor5: 'Ramas menores de 5 mm',
    ramas_mayor5: 'Ramas mayores de 5 mm',
    cortina: 'Cortina',
    hilera: 'Hilera',
    planta: 'Planta',
    piso: 'Piso',
    item: 'Ítem',
    hora: 'Hora',
    nro_muestra: 'Número de muestra',
    diametro: 'Diámetro (mm)',
    diametro_promedio: 'Diámetro medio (mm)',
    diametro_minimo: 'Diámetro mínimo (mm)',
    diametro_maximo: 'Diámetro máximo (mm)',
    cantidad_muestras: 'Muestras registradas',
    grano: 'Unidad de origen',
    revision: 'Revisión',
    publicacion_id: 'Publicación de origen',
    sospechoso: 'Medición sospechosa',
  };
  return Object.entries(data)
    .filter(
      ([key, value]) =>
        ![
          'observaciones',
          'mediciones',
          'total_observaciones',
          'idempotency_key',
          'source_row_hash',
          'source_snapshot_id',
        ].includes(key) &&
        value !== null &&
        value !== '',
    )
    .map(([key, value]) => ({
      label: labels[key] ?? key.replaceAll('_', ' '),
      value:
        key === 'grano'
          ? grainLabel(String(value))
          : typeof value === 'boolean'
            ? value
              ? 'Sí'
              : 'No'
            : formatCell(value),
    }));
}

export function observationsFor(
  data: Record<string, unknown>,
  key: string,
): Array<Record<string, unknown>> {
  const value = data[key];
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> =>
        Boolean(item && typeof item === 'object'),
      )
    : [];
}
