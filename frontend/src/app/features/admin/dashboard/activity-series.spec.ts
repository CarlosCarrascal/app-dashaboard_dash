import { weeklyCounts, weekRange } from './activity-series';
describe('Actividad semanal',()=>{
 it('agrupa de lunes a domingo, conserva ceros y no usa muestras',()=>{
  expect(weeklyCounts([{key:'2026-09-06',evaluations:2},{key:'2026-09-07',evaluations:3},{key:'2026-09-08',evaluations:0},{key:'2026-09-20',evaluations:99}], '2026-08-31','2026-09-14')).toEqual([2,3,0]);
 });
 it('mantiene semanas vacías y cruces de año',()=>{
  expect(weekRange('2025-12-30','2026-01-12')).toEqual(['2025-12-29','2026-01-05','2026-01-12']);
  expect(weeklyCounts([],'2025-12-30','2026-01-12')).toEqual([0,0,0]);
 });
});
