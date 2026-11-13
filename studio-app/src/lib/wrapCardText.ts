/** Conservatively wrap text for fixed-size canvas cards without losing characters. */
export function wrapCardText(text:string,width=20):string {
  return text.split('\n').map(line=>line.split(/\s+/).filter(Boolean).flatMap(word=>{
    const chars=Array.from(word),chunks:string[]=[];
    for(let i=0;i<chars.length;i+=width)chunks.push(chars.slice(i,i+width).join(''));
    return chunks;
  }).reduce((lines,word)=>{
    if(!lines.length || lines[lines.length-1].length+1+word.length>width)lines.push(word);
    else lines[lines.length-1]+=' '+word;
    return lines;
  },[] as string[]).join('\n')).join('\n');
}
