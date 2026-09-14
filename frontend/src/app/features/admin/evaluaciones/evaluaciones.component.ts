import { ChangeDetectionStrategy, Component, inject, OnInit } from '@angular/core';
import { AppIconComponent } from '../../../shared/ui/app-icon.component';
import { FieldButtonDirective } from '../../../shared/ui/field-primitives';
import { CargasComponent } from '../cargas/cargas.component';
import { EvaluationAnalysisComponent } from './analisis/evaluation-analysis.component';
import { EvaluationData } from './datos/evaluation-data.service';
import { EvaluationDetailComponent } from './detalle/evaluation-detail.component';
import { EvaluationWorkspace } from './evaluation-workspace.service';
import { EvaluationFiltersComponent } from './filtros/evaluation-filters.component';
import { EvaluationRecordsComponent } from './registros/evaluation-records.component';
@Component({
  selector: 'app-evaluaciones',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    AppIconComponent,
    FieldButtonDirective,
    CargasComponent,
    EvaluationFiltersComponent,
    EvaluationAnalysisComponent,
    EvaluationRecordsComponent,
    EvaluationDetailComponent,
  ],
  providers: [EvaluationWorkspace, EvaluationData],
  templateUrl: './evaluaciones.component.html',
  styles: [':host {display:block;min-width:0;}'],
})
export class EvaluacionesComponent implements OnInit {
  readonly vm = inject(EvaluationWorkspace);
  ngOnInit(): void {
    this.vm.ngOnInit();
  }
}
