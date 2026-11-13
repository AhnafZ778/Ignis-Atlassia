import { expect, it } from 'vitest';
import { figureSelection } from './figureSelection';

it('exports the whole drawing when no objects are selected', () => {
  const objects = [{ id:'a' }, { id:'b' }];
  expect(figureSelection(objects, {})).toEqual(objects);
});
it('keeps frame contents and bound labels with a selected frame', () => {
  const objects = [{ id:'frame' }, { id:'shape', frameId:'frame' }, { id:'label', containerId:'shape' }, { id:'other' }];
  expect(figureSelection(objects, { frame:true }).map((x) => x.id)).toEqual(['frame','shape','label']);
});
it('does not export unrelated objects with a selection', () => {
  const objects = [{ id:'shape' }, { id:'label', containerId:'shape' }, { id:'other' }];
  expect(figureSelection(objects, { shape:true }).map((x) => x.id)).toEqual(['shape','label']);
});
