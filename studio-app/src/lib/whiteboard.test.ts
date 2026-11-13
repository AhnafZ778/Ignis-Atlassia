import { describe, expect, it } from 'vitest';
import { sceneChanges, sceneObjects } from './whiteboard';

describe('whiteboard changes', () => {
  it('sends only changed objects and retains unrelated drawings', () => {
    const previous = sceneObjects({ elements: [{ id: 'a', x: 1 }, { id: 'b', x: 2 }], files: {} });
    const next = sceneObjects({ elements: [{ id: 'a', x: 4 }, { id: 'b', x: 2 }], files: {} });
    expect(sceneChanges(previous, next)).toEqual([{ kind: 'element', id: 'a', value: { id: 'a', x: 4 }, position: 0 }]);
  });
  it('records deleted elements and file identities', () => {
    const previous = sceneObjects({ elements: [{ id: 'a' }], files: { image: { id: 'image', dataURL: 'x' } } });
    const next = sceneObjects({ elements: [], files: {} });
    expect(sceneChanges(previous, next)).toEqual([
      { kind: 'element', id: 'a', value: null, position: 0 },
      { kind: 'file', id: 'image', value: null, position: 0 }
    ]);
  });
});
