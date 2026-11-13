import {it,expect} from 'vitest';
import {requestsMapLabels} from './boardActionIntent';
it('lets the research agent handle acquisition plus labels and comparisons',()=>{
  expect(requestsMapLabels('Show a heatmap for Dhaka and label the detections.')).toBe(false);
  expect(requestsMapLabels('Find the peak month for Dhaka and mark detections on a heatmap.')).toBe(false);
  expect(requestsMapLabels('Compare heatmaps for these regions and annotate the differences.')).toBe(false);
  expect(requestsMapLabels('Label the thermal detections on the heatmap.')).toBe(true);
});
