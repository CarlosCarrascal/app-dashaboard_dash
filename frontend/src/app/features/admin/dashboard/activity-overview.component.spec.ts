import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';
import { vi } from 'vitest';
import { ApiClient } from '../../../core/api/api-client.service';
import { EvaluationData } from '../evaluaciones/datos/evaluation-data.service';
import { ActivityOverviewComponent } from './activity-overview.component';
describe('Consulta de actividad',()=>{
 it('mantiene la opción visible al crear y cambiar los selectores',async()=>{
  const pending=new Subject<any>();
  TestBed.configureTestingModule({imports:[ActivityOverviewComponent],providers:[
   {provide:ApiClient,useValue:{evaluationAnalytics:()=>pending}},
   {provide:Router,useValue:{}}
  ]});
  TestBed.overrideComponent(ActivityOverviewComponent,{set:{providers:[{provide:EvaluationData,useValue:{loadCatalog:()=>of({items:[]})}}]}});
  await TestBed.compileComponents();
  const fixture=TestBed.createComponent(ActivityOverviewComponent);
  fixture.componentInstance.weeks.set(24);
  fixture.componentInstance.family.set('flores');
  fixture.detectChanges();await fixture.whenStable();
  const period=fixture.nativeElement.querySelector('select[aria-label="Periodo del gráfico"]') as HTMLSelectElement;
  const family=fixture.nativeElement.querySelector('select[aria-label="Tipo de evaluación"]') as HTMLSelectElement;
  expect(period.value).toBe('24');expect(family.value).toBe('flores');
  period.value='8';period.dispatchEvent(new Event('change'));fixture.detectChanges();await fixture.whenStable();
  expect(fixture.componentInstance.weeks()).toBe(8);expect(period.value).toBe('8');
  fixture.destroy();
 },15000);
 it('conserva ámbito, origen y periodo en todas las consultas y enlaces',()=>{
  const analytics=vi.fn((q:any,trend:boolean)=>of(trend?{trend:[{key:'2026-09-14',evaluations:4}]}:{hasta:'2026-09-14',grano:'registro_access',grains:['registro_access']}));
  const summary=vi.fn(()=>of({total:4,lotes:2,evaluadores:1,por_modulo:[],ultima_captura:'2026-09-14'}));
  TestBed.configureTestingModule({providers:[{provide:ApiClient,useValue:{evaluationAnalytics:analytics,evaluationCounts:summary}},{provide:EvaluationData,useValue:{loadCatalog:()=>of({items:[{fundo_id:2,codigo:'Fundo 1'}]})}},{provide:Router,useValue:{navigate:vi.fn()}}]});
  const c=TestBed.runInInjectionContext(()=>new ActivityOverviewComponent());c.load();
  expect(c.loading()).toBe(false);expect(c.lines()[0].values.at(-1)).toBe(4);
  expect(summary).toHaveBeenCalledWith({module_key:'estadios',desde:'2026-06-29',hasta:'2026-09-14',grano:'registro_access'});
  expect(c.recordQuery('2026-09-14',2)).toMatchObject({desde:'2026-09-14',hasta:'2026-09-14',fundo_id:2,grano:'registro_access'});
 });
 it('descarta la respuesta anterior al cambiar de familia',()=>{
  const old=new Subject<any>();
  TestBed.configureTestingModule({providers:[{provide:ApiClient,useValue:{evaluationAnalytics:(q:any)=>q.module_key==='estadios'?old:of({hasta:null,grano:null,grains:[]})}},{provide:EvaluationData,useValue:{loadCatalog:()=>of({items:[]})}},{provide:Router,useValue:{}}]});
  const c=TestBed.runInInjectionContext(()=>new ActivityOverviewComponent());c.load();c.changeFamily('pesos');
  old.next({hasta:'2026-09-14',grano:'captura',grains:['captura']});old.complete();
  expect(c.end()).toBe('');expect(c.loading()).toBe(false);expect(c.lines()).toEqual([]);
 });
});
