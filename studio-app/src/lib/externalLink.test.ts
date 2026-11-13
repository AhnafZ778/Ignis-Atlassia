import {expect,it} from 'vitest';
import {externalLinkCard} from './externalLink';

it('creates a labeled reference with the exact web destination',()=>{
  const card=externalLinkCard('https://example.org/paper?q=fire#methods','Fire study','board',10,20);
  expect(card.link).toBe('https://example.org/paper?q=fire#methods');
  expect(card.label.text).toContain('Fire study\nexample.org');
  expect(card.customData.fireatlas).toEqual({documentId:'board',kind:'external-link'});
});

it('accepts only bounded web addresses without credentials',()=>{
  for(const address of ['javascript:alert(1)','file:///tmp/a','https://user:pass@example.org','not a url','https://example.org/'+ 'a'.repeat(2100)])
    expect(()=>externalLinkCard(address,'',null,0,0)).toThrow();
  expect(externalLinkCard('https://example.org/path','',null,0,0).label.text).toContain('example.org');
});
