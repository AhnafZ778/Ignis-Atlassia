/** Mirror the server's bounded whole-board note selection for source navigation. */
export function boardNoteIds(elements: readonly any[], documentId: string): string[] {
  const live = elements.filter(item => !item.isDeleted);
  const byId = new Map(live.map(item => [item.id, item]));
  const candidates = (item:any) => [item,byId.get(item.containerId),byId.get(item.frameId)];
  const assistantPlaced = (item: any): boolean => candidates(item).some(candidate => {
    const ref = candidate?.customData?.fireatlas;
    return ref?.documentId === documentId && typeof ref.kind === 'string' && ref.kind.startsWith('assistant-');
  });
  const dataDisplay = (item:any):boolean => candidates(item).some(candidate=>{
    const ref=candidate?.customData?.fireatlas;
    return ref?.documentId===documentId && ['park-platform-chart','comparison-chart','dataset-group-chart','dataset-group-summary','scatter-values-table'].includes(ref.kind);
  });
  const notes = live.filter(item => item.type === 'text' && typeof item.text === 'string' && item.text.trim());
  return [...notes.filter(item => !assistantPlaced(item) && !dataDisplay(item)),
    ...notes.filter(item => !assistantPlaced(item) && dataDisplay(item)),
    ...notes.filter(assistantPlaced)].slice(0, 20).map(item => item.id);
}
