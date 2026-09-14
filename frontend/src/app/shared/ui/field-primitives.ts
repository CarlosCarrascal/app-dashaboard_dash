import { Directive } from '@angular/core';
@Directive({
  selector: 'button[appFieldButton]',
  standalone: true,
  host: { class: 'field-button' },
})
export class FieldButtonDirective {}
@Directive({ selector: '[appFieldPanel]', standalone: true, host: { class: 'field-panel' } })
export class FieldPanelDirective {}
