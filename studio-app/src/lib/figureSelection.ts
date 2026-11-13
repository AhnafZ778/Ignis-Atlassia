/** Include frame contents and text bound to selected shapes in a figure export. */
export function figureSelection<T extends { id: string; frameId?: string | null; containerId?: string | null }>(elements: readonly T[], selected: Record<string, boolean>): T[] {
  if (!Object.values(selected).some(Boolean)) return [...elements];
  const included = new Set(elements.filter((item) => selected[item.id] || (item.frameId && selected[item.frameId])).map((item) => item.id));
  return elements.filter((item) => included.has(item.id) || (item.containerId && included.has(item.containerId)));
}
