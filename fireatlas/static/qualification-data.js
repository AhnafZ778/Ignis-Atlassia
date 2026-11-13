/* Immutable release identity and exact-byte verification shared by workspaces. */
window.FireAtlasQualification={async read(name,fetcher=window.fetch.bind(window)){
 const base=new URL('./data/qualification/',document.baseURI);
 const request=async(url,cache='default')=>{const r=await fetcher(url,{signal:AbortSignal.timeout(45000),cache});if(!r.ok)throw Error('Qualification evidence unavailable ('+r.status+').');return await r.text();};
 const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(x=>x.toString(16).padStart(2,'0')).join('');
 const pointer=JSON.parse(await request(new URL('current.json',base),'no-store'));
 if(!/^[0-9a-f]{64}$/.test(pointer.release_id))throw Error('Invalid qualification release.');
 const release=new URL('releases/'+pointer.release_id+'/',base),manifestRaw=await request(new URL('manifest.json',release));
 if(await hash(manifestRaw)!==pointer.manifest_sha256)throw Error('Publication manifest hash differs.');
 const manifest=JSON.parse(manifestRaw),meta=manifest.files?.[name];
 if(!meta||manifest.release_id!==pointer.release_id||!/^[a-z0-9/.-]+$/.test(name)||name.includes('..'))throw Error('Unsupported qualification artifact.');
 const url=new URL(name,release),raw=await request(url);
 if(new TextEncoder().encode(raw).length!==meta.bytes||await hash(raw)!==meta.sha256)throw Error('Evidence bytes differ from the publication manifest.');
 return {value:JSON.parse(raw),raw,url:url.href,release_id:pointer.release_id};
}};
