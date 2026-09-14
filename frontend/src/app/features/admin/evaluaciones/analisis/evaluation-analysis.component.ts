import { A11yModule } from '@angular/cdk/a11y';
import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AppIconComponent } from '../../../../shared/ui/app-icon.component';
import { FieldButtonDirective, FieldPanelDirective } from '../../../../shared/ui/field-primitives';
import { EvaluationChartComponent } from '../evaluation-chart.component';
import { EvaluationWorkspace } from '../evaluation-workspace.service';

@Component({
  selector: 'app-evaluation-analysis',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe,
    A11yModule,
    AppIconComponent,
    FieldButtonDirective,
    FieldPanelDirective,
    EvaluationChartComponent,
  ],
  templateUrl: './evaluation-analysis.component.html',
  styles: [':host {display:contents}'],
})
export class EvaluationAnalysisComponent {
  readonly vm = inject(EvaluationWorkspace);
}
