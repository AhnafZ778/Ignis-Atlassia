export type GroupFocus={datasetId:string;groupColumn:string;valueColumn:string;name:string|null};

/** Match the clicked figure value to the same recalculated grouped result. */
export function groupIsFocused(focus:GroupFocus|null,datasetId:string,groupColumn:string,valueColumn:string,name:string|null):boolean {
  return focus?.datasetId===datasetId && focus.groupColumn===groupColumn && focus.valueColumn===valueColumn && focus.name===name;
}
