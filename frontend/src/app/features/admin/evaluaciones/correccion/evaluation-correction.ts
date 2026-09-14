import { DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder } from '@angular/forms';
import { ApiClient } from '../../../../core/api/api-client.service';
import type {
  AdminEvaluationDetail,
  EvaluationCorrectionRequest,
} from '../../../../core/api/models';
import { observationsFor } from '../evaluation-format';
import type { EvaluationWorkspace } from '../evaluation-workspace.service';
type Host = Pick<
  EvaluationWorkspace,
  | 'canEditEvaluations'
  | 'observations'
  | 'detailLoading'
  | 'selected'
  | 'errorMessage'
  | 'messageFor'
  | 'numberValue'
  | 'successMessage'
  | 'refreshAfterCorrection'
  | 'detailColumnLabel'
>;
/** Feature-specific controller. The host coordinates navigation and refresh after mutations. */
export class EvaluationCorrection {
  constructor(private readonly getHost: () => Host) {}
  private get host(): Host {
    return this.getHost();
  }
  private readonly formBuilder = inject(FormBuilder);
  private readonly api = inject(ApiClient);
  private readonly destroyRef = inject(DestroyRef);
  readonly editing = signal(false);

  readonly saving = signal(false);

  readonly correctionForm = this.formBuilder.nonNullable.group({
    fecha: '',
    lote_id: 0,
    cortina: 0,
    hilera: 0,
    planta: 0,
    nro_muestra: 0,
    evaluador_id: 0,
    item: '',
    piso: '',
    hora: '',
    valores: this.formBuilder.array<ReturnType<typeof this.createValueControl>>([]),
    comentario: '',
  });

  canCorrect(): boolean {
    return this.host.canEditEvaluations();
  }

  canCorrectDetail(detail: AdminEvaluationDetail): boolean {
    if (detail.source_table === 'ev_evaluacion' && detail.detalle?.['publicacion_id'] != null)
      return false;
    return (
      this.canCorrect() &&
      !(detail.source_table === 'ev_baya_medicion' && this.host.observations(detail).length > 1)
    );
  }

  startCorrection(detail: AdminEvaluationDetail): void {
    if (detail.detalle?.['total_observaciones'] !== undefined) {
      this.host.detailLoading.set(true);
      this.api
        .evaluationDetail(detail.module_key, detail.source_id, detail.source_table)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (full) => {
            this.host.detailLoading.set(false);
            this.host.selected.set(full);
            this.startCorrection(full);
          },
          error: (e) => {
            this.host.detailLoading.set(false);
            this.host.errorMessage.set(this.host.messageFor(e));
          },
        });
      return;
    }
    const values = detail.detalle ?? {};
    const editable = this.editableValues(detail);
    this.correctionForm.controls.valores.clear();
    for (const [key, value] of Object.entries(editable)) {
      this.correctionForm.controls.valores.push(
        this.createValueControl(key, this.correctionLabel(key), value),
      );
    }
    this.correctionForm.reset({
      fecha: detail.fecha,
      lote_id: this.host.numberValue(detail.lote_id),
      cortina: this.host.numberValue(values['cortina']),
      hilera: this.host.numberValue(values['hilera']),
      planta: this.host.numberValue(values['planta']),
      nro_muestra: this.host.numberValue(values['nro_muestra']),
      evaluador_id: this.host.numberValue(detail.evaluador_id),
      item: String(values['item'] ?? ''),
      piso: String(values['piso'] ?? ''),
      hora: String(values['hora'] ?? ''),
      comentario: '',
    });
    this.host.errorMessage.set(null);
    this.editing.set(true);
  }

  cancelCorrection(): void {
    this.editing.set(false);
  }

  submitCorrection(): void {
    const detail = this.host.selected();
    if (!detail) return;
    const raw = this.correctionForm.getRawValue();
    const values = Object.fromEntries(
      raw.valores.map((item) => [item.key, this.coerceCorrectionValue(item.value)]),
    );
    const payload: EvaluationCorrectionRequest = {
      source_table: detail.source_table as EvaluationCorrectionRequest['source_table'],
      fecha: raw.fecha,
      lote_id: raw.lote_id,
      cortina: raw.cortina || null,
      hilera: raw.hilera || null,
      planta: raw.planta || null,
      nro_muestra: raw.nro_muestra || null,
      evaluador_id: raw.evaluador_id || null,
      item: raw.item || null,
      piso: raw.piso || null,
      hora: raw.hora || null,
      valores: values,
      comentario: raw.comentario || null,
      idempotency_key: crypto.randomUUID(),
    };
    this.saving.set(true);
    this.host.errorMessage.set(null);
    this.api.correctEvaluation(detail.module_key, detail.source_id, payload).subscribe({
      next: (response) => {
        this.host.selected.set(response.evaluacion);
        this.editing.set(false);
        this.saving.set(false);
        this.host.successMessage.set('Corrección guardada y auditada correctamente.');
        this.host.refreshAfterCorrection();
      },
      error: (error: unknown) => {
        this.saving.set(false);
        this.host.errorMessage.set(
          this.host.messageFor(error, 'No se pudo guardar la corrección.'),
        );
      },
    });
  }

  editableValues(detail: AdminEvaluationDetail): Record<string, unknown> {
    const data = detail.detalle ?? {};
    const values: Record<string, unknown> = {};
    if (detail.source_table === 'ev_baya_medicion') {
      return { diametro: data['diametro'], sospechoso: data['sospechoso'] ?? false };
    }
    if (detail.module_key === 'estadios') {
      for (let index = 1; index <= 5; index += 1) values[`m1_e${index}`] = data[`e${index}`] ?? 0;
      values['m1_total'] = data['total_origen'];
    } else if (detail.module_key === 'flores') {
      const names: Record<string, string> = {
        n_flores: 'm2_flores',
        cuajo: 'm2_cuajos',
        yemas_abiertas: 'm2_ya',
        yemas_por_abrir: 'm2_yp',
        yemas_muertas: 'm2_ymuerta',
        brotes_tiernos: 'm2_brotes_tiernos',
      };
      for (const [source, target] of Object.entries(names)) values[target] = data[source] ?? 0;
    } else if (detail.module_key === 'brotes') {
      values['m6_piso'] = data['piso'];
      values['m6_brotes'] = data['brotes'] ?? 0;
      values['m6_des1'] = data['des1'];
      values['m6_des2'] = data['des2'];
      values['m6_des3'] = data['des3'];
    } else if (detail.module_key === 'ramas') {
      values['m7_ram_lt5'] = data['ramas_menor5'] ?? 0;
      values['m7_ram_gt5'] = data['ramas_mayor5'] ?? 0;
      for (const item of observationsFor(data, 'mediciones')) {
        const number = this.host.numberValue(item['nro_rama']);
        if (number) values[`m7_diam${String(number).padStart(2, '0')}`] = item['diametro'];
      }
    } else {
      const prefix = detail.module_key === 'pesos' ? 'm5' : 'm4';
      for (const item of observationsFor(data, 'observaciones')) {
        const number = this.host.numberValue(item['numero_muestra']);
        if (!number) continue;
        if (prefix === 'm4') {
          values[`m4_est${String(number).padStart(2, '0')}`] = item['estado_codigo'];
          values[`m4_diam${String(number).padStart(2, '0')}`] = item['diametro_mm'];
        } else {
          values[`m5_peso${String(number).padStart(2, '0')}`] = item['peso_g'];
          values[`m5_diam${String(number).padStart(2, '0')}`] = item['diametro_mm'];
        }
      }
    }
    return values;
  }

  createValueControl(key = '', label = '', value: unknown = '') {
    return this.formBuilder.nonNullable.group({ key, label, value: String(value ?? '') });
  }

  correctionLabel(key: string): string {
    const normalized = key
      .replace(/^m[1-7]_/, '')
      .replace(/^diam0?/, 'diámetro ')
      .replace(/^peso0?/, 'peso ')
      .replace(/^est0?/, 'estado ');
    return this.host.detailColumnLabel(normalized) === normalized
      ? normalized.replaceAll('_', ' ').replace(/^\w/, (letter) => letter.toUpperCase())
      : this.host.detailColumnLabel(normalized);
  }

  coerceCorrectionValue(value: string): unknown {
    const trimmed = value.trim();
    if (trimmed === '') return null;
    if (trimmed === 'true' || trimmed === 'false') return trimmed === 'true';
    const number = Number(trimmed);
    return Number.isFinite(number) ? number : trimmed;
  }
}
