import templates from '../../../fireatlas/studio/audience_templates.json';
import type { Chapter, StoryBody } from '../types';
export function adaptAudience(body: StoryBody, audience: NonNullable<StoryBody['audience']>): StoryBody {
  return { ...body, audience, chapters: body.chapters.map((chapter: Chapter) => {
    const purpose = chapter.narration_template;
    if (!purpose) return chapter;
    const profiles = templates.profiles as Record<string, Record<string, string>>;
    const known = Object.values(profiles).some((profile) => profile[purpose] === chapter.narration);
    if (!known || chapter.narration_segments?.length) return { ...chapter, narration_template: null };
    return { ...chapter, narration: profiles[audience][purpose] };
  }) };
}
