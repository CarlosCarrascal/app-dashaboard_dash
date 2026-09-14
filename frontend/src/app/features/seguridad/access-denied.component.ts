import { Component } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { RouterLink } from '@angular/router';
import { AppIconComponent } from '../../shared/ui/app-icon.component';

@Component({
  selector: 'app-access-denied',
  standalone: true,
  imports: [AppIconComponent, MatButtonModule, MatCardModule, RouterLink],
  template: `
    <main class="access-page">
      <mat-card>
        <app-icon name="quality" />
        <h1>Acceso restringido</h1>
        <p>Tu sesión es válida, pero no tiene permiso para abrir este módulo.</p>
        <a mat-flat-button color="primary" routerLink="/admin">Volver al resumen</a>
      </mat-card>
    </main>
  `,
  styles: `
    .access-page { display: grid; min-height: 100%; place-items: center; padding: 32px; background: var(--aa-background); }
    mat-card { display: flex; max-width: 430px; align-items: center; gap: 12px; padding: 32px; border: 1px solid var(--aa-border); text-align: center; }
    app-icon { color: var(--aa-accent-deep); width: 34px; height: 34px; }
    h1 { margin: 0; color: var(--aa-ink); font-size: 1.35rem; }
    p { margin: 0 0 12px; color: var(--aa-muted); line-height: 1.5; }
  `,
})
export class AccessDeniedComponent {}
