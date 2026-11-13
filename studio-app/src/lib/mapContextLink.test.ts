import {expect,it} from 'vitest';
import {mapContextLink} from './mapContextLink';

it('links the saved scope, day and source to the current interactive map',()=>{
  const scope={bbox:[-122.2,38.8,-120,41],start:'2024-08-01',end:'2024-08-31'};
  const receipt={operation:'replay',payload:{frames:[{date_utc:'2024-08-10'}]}};
  const link=mapContextLink(scope,'2024-08-10','MODIS_SP',receipt)!;
  const params=new URL(link,'https://example.test/').searchParams;
  expect(params.get('bbox')).toBe('-122.2,38.8,-120,41');expect(params.get('day')).toBe('2024-08-10');
  expect(params.get('source')).toBe('MODIS_SP');expect(params.get('series')).toBe('modis');expect(params.get('start')).toBe(scope.start);
  expect(mapContextLink(scope,'2024-08-11','MODIS_SP',receipt)).toBeNull();
  expect(mapContextLink(scope,'2024-08-10','other',receipt)).toBeNull();
  expect(mapContextLink(scope,'2024-08-10','joint',{operation:'research'})).toBeNull();
});
