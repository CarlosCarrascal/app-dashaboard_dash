import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AppIconComponent } from '../../../../shared/ui/app-icon.component';
import { FieldButtonDirective } from '../../../../shared/ui/field-primitives';
import { EvaluationWorkspace } from '../evaluation-workspace.service';

@Component({
  selector: 'app-evaluation-records',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, AppIconComponent, FieldButtonDirective],
  templateUrl: './evaluation-records.component.html',
  styles: [':host {display:contents}'],
})
export class EvaluationRecordsComponent {
  readonly vm = inject(EvaluationWorkspace);
}
