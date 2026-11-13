import { expect, it } from 'vitest';
import { buildReport, parseCsv, sanitizeFigure } from './investigationReport';

it('preserves CSV quoting, newlines, empty fields and zero values',()=>{
  expect(parseCsv('\ufeffname,value,comment\r\n"A, B",0,"line 1\nline ""2"""\r\nclear,,ok\r\n')).toEqual([
    ['name','value','comment'],['A, B','0','line 1\nline "2"'],['clear','','ok']]);
});
it('escapes user content and includes exact embedded original CSV',()=>{
  const csv=new TextEncoder().encode('name,value\n<script>,0\n');
  const html=buildReport('<title>','<svg xmlns="http://www.w3.org/2000/svg"></svg>',['<script>bad</script>'],[{name:'data.csv',sha256:'hash',kind:'csv',bytes:csv}]);
  expect(html).not.toContain('<script>');expect(html).toContain('&lt;script&gt;');
  expect(html).toContain('data:text/csv;base64,'+btoa('name,value\n<script>,0\n'));
  expect(html).toContain('<td>0</td>');
});
it('removes executable SVG content and unsafe links',()=>{
  const svg=new DOMParser().parseFromString('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><a href="https://bad.example"><text onclick="bad()">A</text></a><image href="data:image/png;base64,eA=="/></svg>','image/svg+xml').documentElement as unknown as SVGSVGElement;
  const result=sanitizeFigure(svg);
  expect(result).not.toContain('<script');expect(result).not.toContain('onclick');expect(result).not.toContain('https://bad.example');expect(result).toContain('data:image/png;base64,eA==');
});
it('limits large table previews while preserving the complete CSV download',()=>{
  const text=Array.from({length:1200},(_,i)=>`${i},`+'x,'.repeat(29)+'end').join('\n')+'\n';
  const html=buildReport('Large','<svg></svg>',[],[{name:'large.csv',sha256:'hash',kind:'csv',bytes:new TextEncoder().encode(text)}]);
  expect(html).toContain('First 100 rows shown');
  expect(html).not.toContain('<td>1199</td>');
  expect(html).toContain('data:text/csv;base64,'+btoa(text));
});
it('includes the complete evidence receipt and a safely escaped readable preview',()=>{
  const source=JSON.stringify({snapshot:{id:'snap'},receipt:{payload:{values:[0,23],note:'<script>bad</script>'}}});
  const html=buildReport('Investigation','<svg></svg>',[],[{name:'evidence.json',sha256:'hash',kind:'evidence',bytes:new TextEncoder().encode(source)}]);
  expect(html).toContain('View evidence data');
  expect(html).toContain('&lt;script&gt;bad&lt;/script&gt;');
  expect(html).toContain('data:application/json;base64,'+btoa(source));
});

it('serializes exporter namespaces as valid standalone XML without changing the original',()=>{
  const ns='http://www.w3.org/2000/svg';
  const svg=document.createElementNS(ns,'svg');
  svg.setAttribute('xmlns',ns);
  const group=document.createElementNS(ns,'g');
  group.setAttributeNS(ns,'clip-path','url(#frame)');
  group.setAttributeNS(ns,'onclick','bad()');
  svg.appendChild(group);
  const result=sanitizeFigure(svg);
  const parsed=new DOMParser().parseFromString(result,'image/svg+xml');
  expect(parsed.querySelector('parsererror')).toBeNull();
  expect(parsed.documentElement.namespaceURI).toBe(ns);
  expect(parsed.querySelector('g')?.getAttribute('clip-path')).toBe('url(#frame)');
  expect(result).not.toContain('onclick');
  expect(svg.getAttribute('xmlns')).toBe(ns);
  expect(group.getAttributeNS(ns,'clip-path')).toBe('url(#frame)');
  expect(sanitizeFigure(parsed.documentElement as unknown as SVGSVGElement)).toBe(result);
});
