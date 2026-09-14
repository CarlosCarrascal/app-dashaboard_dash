import { ChangeDetectionStrategy, Component, Input } from '@angular/core';

const ICON_PATHS: Record<string, readonly string[]> = {
  flower: ['M12 8c-6-9-12 2-4 4-9 6 2 12 4 4 6 9 12-2 4-4 9-6-2-12-4-4Z','M12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4'],
  fruit: ['M12 8c-9-6-12 10-3 13h6c9-3 6-19-3-13Z','M12 8V3','M12 5c1-3 4-3 6-2-1 3-4 3-6 2'],
  weight: ['M9 7a3 3 0 1 1 6 0','M6 8h12l3 13H3Z','M9 15h6'],
  branches: ['M12 22V3','M12 16 5 9V4','M12 12l7-6V2','M12 20l8-5v-4'],
  home: ['M3 10.8 12 3l9 7.8', 'M5.5 9.5V21h13V9.5', 'M9 21v-7h6v7'],
  evaluations: ['M9 5h10a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z', 'M9 9h8', 'M9 13h8', 'M9 17h5', 'M3 7h4', 'M3 12h4', 'M3 17h4'],
  quality: ['M12 3 4.8 6.2v5.3c0 4.6 3 8.2 7.2 9.5 4.2-1.3 7.2-4.9 7.2-9.5V6.2L12 3Z', 'm8.8 12.2 2.1 2.1 4.5-4.7'],
  structure: ['M5 4h6v5H5z', 'M13 15h6v5h-6z', 'M5 15h6v5H5z', 'M8 9v3h8v3', 'M8 12v3'],
  users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  logout: ['M10 17l5-5-5-5', 'M15 12H3', 'M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4'],
  search: ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z', 'm21 21-4.35-4.35'],
  filter: ['M4 5h16', 'M7 12h10', 'M10 19h4'],
  upload: ['M12 16V4', 'm7 9 5-5 5 5', 'M5 20h14'],
  download: ['M12 4v12', 'm7 11 5 5 5-5', 'M5 20h14'],
  close: ['M6 6l12 12', 'M18 6 6 18'],
  chevronDown: ['m6 9 6 6 6-6'],
  chevronRight: ['m9 6 6 6-6 6'],
  chevronLeft: ['m15 6-6 6 6 6'],
  arrowRight: ['M5 12h14', 'm13 6 6 6-6 6'],
  refresh: ['M20 7v5h-5', 'M4 17v-5h5', 'M6.1 9a7 7 0 0 1 11.4-2L20 12', 'M4 12l2.5 5a7 7 0 0 0 11.4-2'],
  check: ['m5 12 4 4L19 6'],
  warning: ['M10.3 4.1 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 4.1a2 2 0 0 0-3.4 0Z', 'M12 9v4', 'M12 17h.01'],
  calendar: ['M6 3v3', 'M18 3v3', 'M4 8h16', 'M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z'],
  clock: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 6v6l4 2'],
  grid: ['M4 4h6v6H4z', 'M14 4h6v6h-6z', 'M4 14h6v6H4z', 'M14 14h6v6h-6z'],
  person: ['M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z', 'M4 21a8 8 0 0 1 16 0'],
  leaf: ['M20 4C11 4 5 8 5 15c0 3 2 5 5 5 7 0 10-8 10-16Z', 'M5 20c3-5 7-8 13-12'],
  more: ['M5 12h.01', 'M12 12h.01', 'M19 12h.01'],
  edit: ['M12 20h9', 'M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z'],
  save: ['M5 4h12l2 2v14H5Z', 'M8 4v6h8V4', 'M8 20v-6h8v6'],
  info: ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Z', 'M12 11v6', 'M12 7h.01'],
};

@Component({
  selector: 'app-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="1.8"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      @for (path of paths; track path) {
        <path [attr.d]="path" />
      }
    </svg>
  `,
  styles: [`
    :host { display: inline-flex; width: 1em; height: 1em; flex: 0 0 auto; }
    svg { display: block; width: 100%; height: 100%; }
  `],
})
export class AppIconComponent {
  @Input({ required: true }) name = 'grid';

  get paths(): readonly string[] {
    return ICON_PATHS[this.name] ?? ICON_PATHS['grid'];
  }
}
