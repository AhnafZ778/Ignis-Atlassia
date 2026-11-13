import { describe, expect, it } from 'vitest';
import { scatterPosition } from './csvScatter';

describe('scatter positions', () => {
  it('handles extreme magnitudes without overflow', () => {
    expect(scatterPosition([-1e308, 0, 1e308])).toEqual([0, 0.5, 1]);
    expect(scatterPosition([1e-310, 2e-310])).toEqual([0, 1]);
  });
  it('centers constant values', () => {
    expect(scatterPosition([0, 0])).toEqual([0.5, 0.5]);
  });
});
