import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { ReactiveFormsModule } from '@angular/forms';
import { FieldButtonDirective } from '../../../../shared/ui/field-primitives';
import { FieldSelectComponent } from '../../../../shared/ui/field-select.component';
import { EvaluationWorkspace } from '../evaluation-workspace.service';

@Component({
  selector: 'app-evaluation-filters',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ReactiveFormsModule, FieldSelectComponent, FieldButtonDirective],
  templateUrl: './evaluation-filters.component.html',
  styles: [':host {display:contents}'],
})
export class EvaluationFiltersComponent {
  readonly vm = inject(EvaluationWorkspace);
}
