import {expect,it} from 'vitest';
import {challengeOriginals} from './challengeNavigation';

it('finds only the original items referenced by the selected board challenge',()=>{
  const original={id:'original'},other={id:'other'},challenge={id:'challenge',customData:{fireatlas:{documentId:'board',originalElementIds:['original','missing','original']}}};
  const result=challengeOriginals([original,other,challenge],{challenge:true},'board');
  expect(result.targets).toEqual([original]);expect(result.missing).toBe(1);
  expect(()=>challengeOriginals([original,other,challenge],{challenge:true},'other-board')).toThrow('Select a challenge');
  expect(()=>challengeOriginals([{...original,isDeleted:true},challenge],{challenge:true},'board')).toThrow('no longer');
});
