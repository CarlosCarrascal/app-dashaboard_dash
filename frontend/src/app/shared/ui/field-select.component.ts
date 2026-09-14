import { Component, Input, Output, EventEmitter } from '@angular/core';

let nextId = 0;
@Component({
  selector: 'app-field-select',
  standalone: true,
  template: `<label class="field-label"
      >{{ label
      }}<input
        class="field-input"
        [attr.list]="id"
        [value]="display()"
        [placeholder]="placeholder"
        (change)="choose($any($event.target).value)"
        autocomplete="off" /><datalist [id]="id">
        <option value="Todos"></option>
        @for (option of options; track option.id) {
          <option [value]="option.label"></option>
        }</datalist
    ></label>
    @if (invalid) {
      <p class="mt-1 text-xs text-red-700" role="alert">Selecciona una opción de la lista.</p>
    }`,
})
export class FieldSelectComponent {
  @Input() label = '';
  @Input() placeholder = 'Buscar…';
  @Input() options: { id: number; label: string }[] = [];
  @Input() value = 0;
  @Output() valueChange = new EventEmitter<number>();
  readonly id = `field-options-${++nextId}`;
  invalid = false;
  display() {
    return this.options.find((o) => o.id === this.value)?.label ?? '';
  }
  choose(text: string) {
    const option = this.options.find((o) => o.label === text);
    this.invalid = !!text && text !== 'Todos' && !option;
    if (!this.invalid) this.valueChange.emit(option?.id ?? 0);
  }
}
