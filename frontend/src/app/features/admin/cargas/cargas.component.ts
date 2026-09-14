import { DatePipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTableModule } from '@angular/material/table';
import { ApiClient } from '../../../core/api/api-client.service';
import { AdminLoadPage, ImportPreview, ImportPreviewRow, ImportResult } from '../../../core/api/models';
import { KpiCardComponent } from '../../../shared/ui/kpi-card.component';
import { PageHeaderComponent } from '../../../shared/ui/page-header.component';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';

type LoadStatus = 'pending_confirmation' | 'processing' | 'accepted' | 'failed';

@Component({
  selector: 'app-cargas',
  standalone: true,
  imports: [
    AppIconComponent,
    DatePipe,
    JsonPipe,
    KpiCardComponent,
    MatButtonModule,
    MatCardModule,
    MatPaginatorModule,
    MatProgressBarModule,
    MatTableModule,
    PageHeaderComponent,
  ],
  templateUrl: './cargas.component.html',
  styleUrl: './cargas.component.scss',
})
export class CargasComponent implements OnInit {
  private readonly api = inject(ApiClient);
  readonly embedded = input(false);

  readonly selectedFile = signal<File | null>(null);
  readonly result = signal<ImportPreview | null>(null);
  readonly confirmation = signal<ImportResult | null>(null);
  readonly loading = signal(false);
  readonly confirming = signal(false);
  readonly errorMessage = signal<string | null>(null);
  readonly history = signal<AdminLoadPage | null>(null);
  readonly historyState = signal<LoadStatus | ''>('');
  readonly historyLoading = signal(false);
  readonly historyError = signal<string | null>(null);
  readonly columns = ['row', 'valid', 'error', 'payload'];
  readonly historyColumns = [
    'archivo_nombre',
    'usuario',
    'estado',
    'filas',
    'creado_en',
    'resultado',
  ];

  previewGroups(rows: ImportPreviewRow[]): Array<{ key: string; label: string; total: number; valid: number; invalid: number }> {
    const groups = new Map<string, { key: string; label: string; total: number; valid: number; invalid: number }>();
    for (const row of rows) {
      const key = String(row.payload?.['modulo'] ?? row.payload?.['module_key'] ?? 'sin_clasificar').toLocaleLowerCase();
      const group = groups.get(key) ?? { key, label: this.familyLabel(key), total: 0, valid: 0, invalid: 0 };
      group.total += 1;
      group.valid += row.valid ? 1 : 0;
      group.invalid += row.valid ? 0 : 1;
      groups.set(key, group);
    }
    return [...groups.values()];
  }

  familyLabel(key: string): string {
    return ({ estadios: 'Conteo de estadios', flores: 'Conteo de flores', baya: 'Desarrollo de fruto', pesos: 'Peso de baya', peso: 'Peso de baya', brotes: 'Conteo de brotes', ramas: 'Conteo de ramas', sin_clasificar: 'Sin clasificar' } as Record<string, string>)[key] ?? key;
  }

  ngOnInit(): void {
    this.loadHistory();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile.set(input.files?.[0] ?? null);
    this.result.set(null);
    this.confirmation.set(null);
    this.errorMessage.set(null);
  }

  confirmFile(): void {
    const preview = this.result();
    if (!preview || preview.invalid_rows > 0) {
      this.errorMessage.set('Solo puedes confirmar una previsualización sin errores.');
      return;
    }
    this.confirming.set(true);
    this.errorMessage.set(null);
    this.api
      .confirmEvaluations({ preview_id: preview.preview_id, file_sha256: preview.file_sha256 })
      .subscribe({
      next: (result) => {
        this.confirmation.set(result);
        this.confirming.set(false);
        this.loadHistory();
      },
      error: (error: unknown) => {
        this.confirming.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
      });
  }

  previewFile(): void {
    const file = this.selectedFile();
    if (!file) {
      this.errorMessage.set('Selecciona un archivo .xlsx antes de previsualizar.');
      return;
    }
    this.loading.set(true);
    this.errorMessage.set(null);
    this.api.previewEvaluations(file).subscribe({
      next: (result) => {
        this.result.set(result);
        this.loading.set(false);
        this.loadHistory();
      },
      error: (error: unknown) => {
        this.loading.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  downloadTemplate(): void {
    this.api.downloadEvaluationTemplate().subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'plantilla_evaluaciones.xlsx';
        anchor.click();
        URL.revokeObjectURL(url);
      },
      error: (error: unknown) => this.errorMessage.set(this.messageFor(error)),
    });
  }

  onHistoryStateChanged(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as LoadStatus | '';
    this.historyState.set(value);
    this.loadHistory(1);
  }

  onHistoryPage(event: PageEvent): void {
    this.loadHistory(event.pageIndex + 1, event.pageSize);
  }

  refreshHistory(): void {
    this.loadHistory();
  }

  loadStatusLabel(status: LoadStatus): string {
    return {
      pending_confirmation: 'Pendiente',
      processing: 'Procesando',
      accepted: 'Aceptada',
      failed: 'Fallida',
    }[status];
  }

  loadStatusClass(status: LoadStatus): string {
    return `load-${status}`;
  }

  private messageFor(error: unknown): string {
    if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
      return error.error.detail;
    }
    return 'No se pudo procesar el archivo. La API solo acepta .xlsx hasta 10 MB.';
  }

  private loadHistory(page = 1, pageSize = this.history()?.meta.page_size ?? 20): void {
    this.historyLoading.set(true);
    this.historyError.set(null);
    this.api
      .listImports({
        page,
        page_size: pageSize,
        estado: this.historyState() || undefined,
      })
      .subscribe({
        next: (response) => {
          this.history.set(response);
          this.historyLoading.set(false);
        },
        error: (error: unknown) => {
          this.historyLoading.set(false);
          this.historyError.set(this.messageFor(error));
        },
      });
  }
}
