export type Scene = { elements: any[]; files: Record<string, any>; appState?: Record<string, unknown> };
export type SceneObject = { kind: 'element' | 'file'; id: string; value: any; position: number };

export function sceneObjects(scene: Scene): Map<string, SceneObject> {
  const objects = new Map<string, SceneObject>();
  scene.elements.forEach((element, position) => {
    objects.set(`element:${element.id}`, { kind: 'element', id: element.id, value: element, position });
  });
  Object.entries(scene.files || {}).forEach(([id, file]) => {
    objects.set(`file:${id}`, { kind: 'file', id, value: file, position: 0 });
  });
  return objects;
}

export function sceneChanges(previous: Map<string, SceneObject>, next: Map<string, SceneObject>): SceneObject[] {
  const changes: SceneObject[] = [];
  for (const [key, value] of next) if (JSON.stringify(previous.get(key)) !== JSON.stringify(value)) changes.push(value);
  for (const [key, value] of previous) if (!next.has(key)) changes.push({ ...value, value: null });
  return changes;
}
