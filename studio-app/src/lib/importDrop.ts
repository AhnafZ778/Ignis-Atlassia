/** Only intercept source files; images and native whiteboard files remain Excalidraw drops. */
export function sourceFileKind(file:Pick<File,'name'|'type'>):'csv'|'pdf'|null {
  const name=file.name.toLowerCase();
  if(name.endsWith('.csv'))return 'csv';
  if(name.endsWith('.pdf'))return 'pdf';
  return null;
}

export function mightContainSources(items:DataTransferItemList):boolean {
  return [...items].some(item=>item.kind==='file' && (!item.type || item.type==='text/csv' || item.type==='application/pdf' || item.type==='application/vnd.ms-excel'));
}
