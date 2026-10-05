import { describe, expect, it } from 'vitest';
import templates from '../../../fireatlas/studio/audience_templates.json';
import { adaptAudience } from './audience';
import type { StoryBody } from '../types';
const body = (): StoryBody => ({ title: 'A checked study', profile: 'briefing-1080p-landscape', audience: 'researcher', target_duration_seconds: 120, chapters: [{
  id: 'chapter', title: 'Activity', narration: templates.profiles.researcher.activity, narration_template: 'activity', caption: 'Authored caption',
  card_id: 'card', duration_seconds: 20, transition: 'fade', evidence_cards: ['card'], selection: { start: '2024-07-24', end: '2024-07-26' }
}] });
describe('audience prose adaptation', () => {
  it('changes marked starter wording while keeping scope, values and authored captions intact', () => {
    const original = body(), adapted = adaptAudience(original, 'student');
    expect(adapted.chapters[0].narration).toBe(templates.profiles.student.activity);
    expect(adapted.chapters[0].selection).toEqual(original.chapters[0].selection);
    expect(adapted.chapters[0].caption).toBe('Authored caption');
    expect(original.chapters[0].narration).toBe(templates.profiles.researcher.activity);
    expect(adaptAudience(adapted, 'reviewer').chapters[0].narration).toBe(templates.profiles.reviewer.activity);
  });
  it('does not rewrite manual text or structured checked narration', () => {
    const original = body(); original.chapters[0].narration = 'My own explanation.';
    expect(adaptAudience(original, 'public').chapters[0]).toMatchObject({ narration: 'My own explanation.', narration_template: null });
    original.chapters[0].narration = templates.profiles.researcher.activity;
    original.chapters[0].narration_segments = [{ kind: 'checked-field', path: '/summary/joint_cell_days', format: 'with-unit' }];
    const adapted = adaptAudience(original, 'presenter');
    expect(adapted.chapters[0].narration_segments).toEqual(original.chapters[0].narration_segments);
    expect(adapted.chapters[0].narration).toBe(original.chapters[0].narration);
  });
});
