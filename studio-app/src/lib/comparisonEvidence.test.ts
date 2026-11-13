import {describe,it,expect} from 'vitest';
import {comparisonEvidence} from './comparisonEvidence';
describe('frozen comparison inspection',()=>{
  const receipt={operation:'regional_comparison',payload:{panels:[2023,2025].map(year=>({label:'Test locality',start:`${year}-05-01`,end:`${year}-05-01`,search_start:`${year}-01-01`,search_end:`${year}-12-31`,product:'VIIRS_NOAA20_SP',rank:1,occupied_cells:2,detections:3,cell_delta:0,tied_dates:[`${year}-05-01`,`${year}-05-02`],weather:{status:'available',source:'ERA5',start:`${year}-04-25`,end:`${year}-05-01`,sha256:'weather-hash',latitude:24,longitude:88,original_response:{latitude:24.25,longitude:88.25}}}))}};
  it('shows the selected later panel and its search, ties and returned reanalysis point',()=>{
    const result=comparisonEvidence(receipt,1)!;
    expect(result).toHaveLength(1);expect(result[0].start).toBe('2025-05-01');expect(result[0].searchStart).toBe('2025-01-01');
    expect(result[0].tiedDates).toContain('2025-05-02');expect(result[0].weather?.latitude).toBe(24.25);
  });
  it('shows every panel for a whole frame and rejects an invalid identity',()=>{
    expect(comparisonEvidence(receipt,undefined)).toHaveLength(2);
    expect(()=>comparisonEvidence(receipt,2)).toThrow('panel changed');expect(()=>comparisonEvidence(receipt,'1')).toThrow('panel changed');
  });
  it('never exposes an imported executable weather link',()=>{
    const altered=structuredClone(receipt);(altered.payload.panels[0].weather as any).url='javascript:alert(1)';
    expect(comparisonEvidence(altered,0)![0].weather?.url).toBeUndefined();
    (altered.payload.panels[0].weather as any).url='https://archive-api.open-meteo.com/v1/archive?latitude=24';
    expect(comparisonEvidence(altered,0)![0].weather?.url).toContain('https://archive-api.open-meteo.com/');
  });
});
