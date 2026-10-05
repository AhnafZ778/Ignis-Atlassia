declare global {
  interface Window {
    L?: any;
    FireAtlasMap?: { createIndex(bundle: unknown): any; frame(index: any, i: number, source?: string, scope?: string): any; install(L: any): any; drawHeat(context: CanvasRenderingContext2D, width: number, height: number, frame: any, project: (point: number[]) => { x: number; y: number }): void };
    FireAtlasContext?: { read(): Record<string, any>; link(path: string, overrides?: Record<string, unknown>): string; apply?(root?: Document | Element, context?: Record<string, any>): void };
  }
}
export {};
