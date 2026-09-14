import { TestBed } from '@angular/core/testing';
import { HttpClient } from '@angular/common/http';
import { of } from 'rxjs';
import { vi } from 'vitest';
import { ApiClient } from './api-client.service';
describe('Shared dashboard reads',()=>{
 let api:ApiClient; let http:{get:ReturnType<typeof vi.fn>;patch:ReturnType<typeof vi.fn>;post:ReturnType<typeof vi.fn>};
 beforeEach(()=>{http={get:vi.fn(()=>of({items:[],meta:{}})),patch:vi.fn(()=>of({})),post:vi.fn(()=>of({}))};TestBed.configureTestingModule({providers:[{provide:HttpClient,useValue:http}]});api=TestBed.inject(ApiClient);});
 it('avoids repeat reads across user, role, quality and master visits',()=>{
  for(let i=0;i<3;i++){api.listUsers().subscribe();api.listRoles().subscribe();api.qualitySummary().subscribe();api.listQuality().subscribe();api.listMaster('lotes').subscribe();}
  expect(http.get).toHaveBeenCalledTimes(5);
 });
 it('normalizes query order but separates pages',()=>{
  api.listMaster('lotes',{page:1,page_size:25}).subscribe();api.listMaster('lotes',{page_size:25,page:1}).subscribe();api.listMaster('lotes',{page:2,page_size:25}).subscribe();expect(http.get).toHaveBeenCalledTimes(2);
 });
 it('invalidates after mutations and explicit refresh/session reset',()=>{
  api.listUsers().subscribe();api.updateUser(1,{activo:false,idempotency_key:'test'}).subscribe();api.listUsers().subscribe();api.clearReadCache();api.listUsers().subscribe();expect(http.get).toHaveBeenCalledTimes(3);
 });
 it('reuses analytical responses and records across workspace recreation', () => {
  const query = {module_key: 'estadios', snapshot: true};
  for (let visit = 0; visit < 3; visit++) {
   api.evaluationAnalytics(query).subscribe();
   api.evaluationAnalytics({...query, desde: '2026-08-01', hasta: '2026-08-26'}, true).subscribe();
   api.listEvaluations({module_key: 'estadios', page: 1}).subscribe();
  }
  expect(http.get).toHaveBeenCalledTimes(3);
  api.evaluationAnalytics({...query, lote_id: 42}).subscribe();
  expect(http.get).toHaveBeenCalledTimes(4);
 });
 it('expires session analytical data and clears it after writes and session reset', () => {
  const clock = vi.spyOn(Date, 'now').mockReturnValue(0);
  try {
   const query = {module_key: 'estadios', snapshot: true};
   api.evaluationAnalytics(query).subscribe();
   clock.mockReturnValue(599_999);
   api.evaluationAnalytics(query).subscribe();
   expect(http.get).toHaveBeenCalledTimes(1);
   clock.mockReturnValue(600_001);
   api.evaluationAnalytics(query).subscribe();
   expect(http.get).toHaveBeenCalledTimes(2);
   api.updateUser(1, {activo: false, idempotency_key: 'test'}).subscribe();
   api.evaluationAnalytics(query).subscribe();
   api.clearReadCache();
   api.evaluationAnalytics(query).subscribe();
   expect(http.get).toHaveBeenCalledTimes(4);
  } finally { clock.mockRestore(); }
 });

});
