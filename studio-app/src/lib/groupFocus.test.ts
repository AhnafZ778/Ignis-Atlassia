import {expect,it} from 'vitest';
import {groupIsFocused} from './groupFocus';

it('highlights only the matching source, columns and group, including blank groups',()=>{
  const focus={datasetId:'table',groupColumn:'region',valueColumn:'count',name:null};
  expect(groupIsFocused(focus,'table','region','count',null)).toBe(true);
  expect(groupIsFocused(focus,'other','region','count',null)).toBe(false);
  expect(groupIsFocused(focus,'table','region','other',null)).toBe(false);
  expect(groupIsFocused(focus,'table','region','count','A')).toBe(false);
});
