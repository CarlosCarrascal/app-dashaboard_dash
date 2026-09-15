import { weeklyScope } from './flower-weekly.component';

describe('Weekly analysis scope', () => {
  it('uses a weekly window for latest-date analysis without dropping the selected lot or evaluator', () => {
    const result=weeklyScope({lote_id:42,evaluador_id:7,desde:'2026-09-14',sort_by:'fecha',module_key:'flores'},true,'captura','2026-09-14','cuajo',12);
    expect(result).toEqual({metric:'cuajo',weeks:12,grano:'captura',hasta:'2026-09-14',lote_id:42,evaluador_id:7});
  });
  it('retains the applied date range and historical origin without mixing in mobile captures', () => {
    const result=weeklyScope({desde:'2026-03-02',fundo_id:2,search:'L046'},false,'registro_access','2026-08-28','n_flores',26);
    expect(result['desde']).toBe('2026-03-02');
    expect(result['grano']).toBe('registro_access');
    expect(result['fundo_id']).toBe(2);
    expect(result['search']).toBe('L046');
  });
});
