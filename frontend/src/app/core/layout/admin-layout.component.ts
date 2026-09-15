import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { A11yModule } from '@angular/cdk/a11y';
import { AuthService } from '../auth/auth.service';
import { EvaluationPreload } from '../api/evaluation-preload.service';
import { AppIconComponent } from '../../shared/ui/app-icon.component';

@Component({
  selector: 'app-admin-layout',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, AppIconComponent, A11yModule],
  template: ` <div class="field-workspace flex h-dvh min-w-0 bg-canvas">
    @if (mobileOpen()) {
      <button
        class="fixed inset-0 z-40 bg-black/25 md:hidden"
        aria-label="Cerrar navegación"
        (click)="mobileOpen.set(false)"
      ></button>
    }
    <aside
      class="z-50 flex shrink-0 flex-col border-r border-line bg-white p-3 transition-[width] max-md:fixed max-md:inset-y-0 max-md:left-0"
      [class]="mobileOpen() ? 'w-56' : expanded() ? 'w-56 max-md:hidden' : 'w-[72px] max-md:hidden'"
      [cdkTrapFocus]="mobileOpen()"
      [cdkTrapFocusAutoCapture]="mobileOpen()"
    >
      <a
        routerLink="/admin"
        class="mb-5 flex h-12 items-center gap-3 px-2 text-forest"
        aria-label="Aquanqa, inicio"
        ><img src="/brand/aquanqa-symbol.svg" class="size-7 shrink-0" width="28" height="28" alt="" aria-hidden="true" />
        @if (expanded() || mobileOpen()) {
          <strong class="text-base">AquAnqa</strong>
        }
      </a>
      <nav aria-label="Inicio y evaluaciones" class="flex flex-col gap-2">
        <a routerLink="/admin" routerLinkActive="!bg-forest !text-white" [routerLinkActiveOptions]="{ exact: true }"
          class="mb-2 flex min-h-11 items-center gap-3 rounded-xl px-3 text-muted hover:bg-canvas"
          title="Inicio" aria-label="Inicio" (click)="mobileOpen.set(false)">
          <app-icon name="home" class="text-xl" />
          @if (expanded() || mobileOpen()) { <span class="text-[13px]">Inicio</span> }
        </a>
        @if (auth.hasPermission('admin:evaluaciones:leer')) {
          <a routerLink="/admin/presentacion" routerLinkActive="!bg-forest !text-white"
            class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-muted hover:bg-canvas"
            title="Presentación de evaluaciones" aria-label="Presentación de evaluaciones" (click)="mobileOpen.set(false)">
            <app-icon name="evaluations" class="text-xl" />
            @if (expanded() || mobileOpen()) { <span class="text-[13px]">Presentación</span> }
          </a>
          @for (item of modules; track item.key) {
            <a
              [routerLink]="'/admin/evaluaciones/' + item.key"
              routerLinkActive="!bg-forest !text-white"
              class="flex min-h-11 items-center gap-3 rounded-xl px-3 text-muted hover:bg-canvas"
              [title]="item.label"
              [attr.aria-label]="item.label"
              (pointerenter)="evaluationPreload.prepare(item.key)"
              (focus)="evaluationPreload.prepare(item.key)"
              (pointerdown)="evaluationPreload.prepare(item.key)"
              (click)="mobileOpen.set(false)"
              ><app-icon [name]="item.icon" class="text-xl" />
              @if (expanded() || mobileOpen()) {
                <span class="whitespace-nowrap text-[13px]">{{ item.label }}</span>
              }
            </a>
          }
        }
      </nav>
      <nav
        aria-label="Administración"
        class="mt-auto flex flex-col gap-1 border-t border-line pt-3"
      >
        @for (item of secondary; track item.route) {
          @if (auth.hasPermission(item.permission)) {
            <a
              [routerLink]="item.route"
              routerLinkActive="!text-forest !bg-canvas"
              class="flex min-h-11 items-center gap-3 rounded-lg px-3 text-muted hover:bg-canvas"
              [title]="item.label"
              [attr.aria-label]="item.label"
              (click)="mobileOpen.set(false)"
              ><app-icon [name]="item.icon" class="text-xl" />
              @if (expanded() || mobileOpen()) {
                <span class="text-[13px]">{{ item.label }}</span>
              }
            </a>
          }
        }
        <button
          class="flex min-h-11 items-center gap-3 rounded-lg px-3 text-muted hover:bg-canvas max-md:hidden"
          (click)="expanded.set(!expanded())"
          [attr.aria-expanded]="expanded()"
          aria-label="Expandir o contraer navegación"
        >
          <app-icon name="menu" class="text-xl" />
          @if (expanded()) {
            <span>Contraer menú</span>
          }
        </button>
        <button
          class="flex min-h-11 items-center gap-3 rounded-lg px-3 text-muted hover:bg-canvas"
          (click)="auth.logout()"
          title="Cerrar sesión"
          aria-label="Cerrar sesión"
        >
          <app-icon name="logout" class="text-xl" />
          @if (expanded() || mobileOpen()) {
            <span>Cerrar sesión</span>
          }
        </button>
      </nav>
    </aside>
    <main class="min-w-0 flex-1 overflow-y-auto">
      <div class="flex h-12 items-center gap-3 border-b border-line bg-white px-3 md:hidden">
        <button class="field-button" aria-label="Abrir módulos" (click)="mobileOpen.set(true)">
          <app-icon name="menu" /></button
        ><span class="font-medium">AquAnqa · Datos de campo</span>
      </div>
      <router-outlet />
    </main>
  </div>`,
})
export class AdminLayoutComponent {
  readonly auth = inject(AuthService);
  readonly evaluationPreload = inject(EvaluationPreload);
  readonly expanded = signal(false);
  readonly mobileOpen = signal(false);
  readonly modules = [
    { key: 'estadios', label: 'Estadios', icon: 'grid' },
    { key: 'flores', label: 'Flores', icon: 'flower' },
    { key: 'baya', label: 'Desarrollo de fruto', icon: 'fruit' },
    { key: 'pesos', label: 'Peso de fruto', icon: 'weight' },
    { key: 'brotes', label: 'Brotes', icon: 'leaf' },
    { key: 'ramas', label: 'Ramas', icon: 'branches' },
  ];
  readonly secondary = [
    { route: '/admin/qa', label: 'QA · Calidad de datos', icon: 'quality', permission: 'admin:qa:leer' },
    {
      route: '/admin/maestros',
      label: 'Maestros',
      icon: 'structure',
      permission: 'admin:maestros:leer',
    },
    {
      route: '/admin/seguridad',
      label: 'Usuarios',
      icon: 'users',
      permission: 'admin:usuarios:gestionar',
    },
  ];
}
