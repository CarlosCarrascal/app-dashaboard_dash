import type { ColumnDef } from '@tanstack/angular-table';
import type { AdminEvaluationItem, ModuleKey } from '../../../../core/api/models';
export const EVALUATION_FAMILIES: {
  key: ModuleKey;
  label: string;
  short: string;
  ordinal: string;
  description: string;
}[] = [
  {
    key: 'estadios',
    label: 'Conteo de estadios',
    short: 'Estadios',
    ordinal: '01',
    description: 'Distribución fenológica E1–E5 por planta.',
  },
  {
    key: 'flores',
    label: 'Conteo de flores',
    short: 'Flores',
    ordinal: '02',
    description: 'Flores, cuajos y estado de yemas por planta.',
  },
  {
    key: 'baya',
    label: 'Desarrollo de fruto',
    short: 'Fruto',
    ordinal: '03',
    description: 'Diámetro y estadio de observaciones agrupadas.',
  },
  {
    key: 'pesos',
    label: 'Peso de fruto',
    short: 'Peso',
    ordinal: '04',
    description: 'Peso y diámetro de 25 muestras por captura.',
  },
  {
    key: 'brotes',
    label: 'Conteo de brotes',
    short: 'Brotes',
    ordinal: '05',
    description: 'Conteo y desarrollo de brotes por piso.',
  },
  {
    key: 'ramas',
    label: 'Conteo de ramas',
    short: 'Ramas',
    ordinal: '06',
    description: 'Calibre y conteo de ramas por planta.',
  },
];
export function columnsFor(moduleKey: ModuleKey | ''): ColumnDef<AdminEvaluationItem>[] {
  const common: ColumnDef<AdminEvaluationItem>[] = [
    { accessorKey: 'fecha', header: 'Fecha', enableHiding: false },
    { accessorKey: 'lote', header: 'Lote', enableHiding: false },
    { accessorKey: 'modulo', header: 'Módulo' },
    { accessorKey: 'fundo', header: 'Fundo' },
    { accessorKey: 'variedad', header: 'Variedad' },
  ];
  const specifics: Record<string, string[]> = {
    estadios: ['e1', 'e2', 'e3', 'e4', 'e5', 'total', 'total_origen'],
    flores: [
      'n_flores',
      'cuajo',
      'yemas_abiertas',
      'yemas_por_abrir',
      'yemas_muertas',
      'brotes_tiernos',
    ],
    brotes: ['piso', 'brotes', 'des1', 'des2', 'des3'],
    ramas: ['ramas_menor5', 'ramas_mayor5'],
    baya: ['cantidad_muestras', 'diametro_promedio', 'mediciones_sospechosas'],
    pesos: ['cantidad_muestras'],
  };
  const extra: ColumnDef<AdminEvaluationItem>[] = (specifics[moduleKey] ?? []).map((key) => ({
    id: key,
    header: detailColumnLabel(key),
    accessorFn: (row) => row.detalle?.[key] ?? '—',
  }));
  if (!moduleKey)
    common.unshift({
      id: 'module_key',
      header: 'Evaluación',
      accessorFn: (row) => familyLabel(row.module_key),
    });
  return [...common, ...extra, { accessorKey: 'evaluador', header: 'Evaluador' }];
}

export function detailColumnLabel(key: string): string {
  return (
    (
      {
        e1: 'E1',
        e2: 'E2',
        e3: 'E3',
        e4: 'E4',
        e5: 'E5',
        total: 'Total',
        n_flores: 'Flores',
        cuajo: 'Cuajos',
        yemas_abiertas: 'Yemas abiertas',
        yemas_por_abrir: 'Por abrir',
        yemas_muertas: 'Muertas',
        brotes_tiernos: 'Brotes tiernos',
        piso: 'Piso',
        brotes: 'Brotes',
        des1: 'Des1 · origen',
        des2: 'Des2 · origen',
        des3: 'Des3 · origen',
        ramas_menor5: '< 5 mm',
        ramas_mayor5: '> 5 mm',
        nro_muestra: 'Muestra',
        diametro: 'Diámetro',
        sospechoso: 'Sospechosa',
        cantidad_muestras: 'Muestras',
        diametro_promedio: 'Diámetro medio',
        mediciones_sospechosas: 'Sospechosas',
      } as Record<string, string>
    )[key] ?? key
  );
}

export function familyLabel(key: string): string {
  return EVALUATION_FAMILIES.find((item) => item.key === key)?.label ?? key;
}

export function familyDescription(key: string): string {
  return EVALUATION_FAMILIES.find((item) => item.key === key)?.description ?? '';
}

export function familyOrdinal(key: string): string {
  return EVALUATION_FAMILIES.find((item) => item.key === key)?.ordinal ?? '—';
}
