import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { FieldButtonDirective } from '../../../../shared/ui/field-primitives';
import { EvaluationWorkspace } from '../evaluation-workspace.service';

@Component({
  selector: 'app-evaluation-correction',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FieldButtonDirective],
  templateUrl: './evaluation-correction.component.html',
  styles: [':host {display:contents}'],
})
export class EvaluationCorrectionComponent {
  readonly vm = inject(EvaluationWorkspace);
}
