import { A11yModule } from '@angular/cdk/a11y';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AppIconComponent } from '../../../../shared/ui/app-icon.component';
import { FieldButtonDirective } from '../../../../shared/ui/field-primitives';
import { EvaluationCorrectionComponent } from '../correccion/evaluation-correction.component';
import { EvaluationWorkspace } from '../evaluation-workspace.service';
@Component({
  selector: 'app-evaluation-detail',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [A11yModule, AppIconComponent, FieldButtonDirective, EvaluationCorrectionComponent],
  templateUrl: './evaluation-detail.component.html',
  styles: [':host {display:contents}'],
})
export class EvaluationDetailComponent {
  readonly vm = inject(EvaluationWorkspace);
}
