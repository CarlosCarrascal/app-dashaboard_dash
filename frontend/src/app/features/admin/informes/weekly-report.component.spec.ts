import { isoWeekLabel, reportOptions, WeeklyReport } from './weekly-report.component';

describe('Weekly presentation series',()=>{
  it('preserves zero, leaves missing weeks as gaps and keeps module series separate',()=>{
    const points=[
      {week:'2026-09-07',fundo_id:1,fundo:'F1',modulo_id:1,modulo:'M01',evaluations:2,available:2,total:0,mean:0},
      {week:'2026-09-21',fundo_id:1,fundo:'F1',modulo_id:1,modulo:'M01',evaluations:2,available:0,total:null,mean:null},
      {week:'2026-09-07',fundo_id:1,fundo:'F1',modulo_id:2,modulo:'M02',evaluations:1,available:1,total:5,mean:5},
    ];
    const report:WeeklyReport={metric:'n_flores',unit:'conteo por evaluación',desde:'2026-09-07',hasta:'2026-09-21',grano:'captura',grains:['captura'],points};
    const options=reportOptions(report,points);
    const series=options.series as any[];
    expect(series).toHaveLength(2);
    expect(series[0].data.map((p:any)=>p.value)).toEqual([0,null,null]);
    expect(series[0].connectNulls).toBe(false);
    expect(series[1].data[0]).toEqual({value:5,lot:'2|2026-09-07'});
  });
  it('uses ISO weeks correctly across a calendar year boundary',()=>{
    expect(isoWeekLabel('2020-12-28')).toBe('S53');
    expect(isoWeekLabel('2021-01-04')).toBe('S01');
    expect(isoWeekLabel('2026-08-31')).toBe('S36');
  });
});
