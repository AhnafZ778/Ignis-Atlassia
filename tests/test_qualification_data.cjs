const assert=require('node:assert/strict'),test=require('node:test'),fs=require('node:fs'),vm=require('node:vm');
const {createHash,webcrypto}=require('node:crypto');
const sha=value=>createHash('sha256').update(value).digest('hex');

test('moving release pointer bypasses cache while frozen artifacts retain exact bytes and subpath',async()=>{
 const files=new Map(),pointers={},cache=new Map(),calls=[];let current='a';
 for(const letter of ['a','b']){
  const id=letter.repeat(64),body=JSON.stringify({release:letter,units:'observed centroid cell-days'}),manifest=JSON.stringify({release_id:id,files:{'readiness.json':{bytes:Buffer.byteLength(body),sha256:sha(body)}}});
  files.set('releases/'+id+'/manifest.json',manifest);files.set('releases/'+id+'/readiness.json',body);pointers[letter]=JSON.stringify({release_id:id,manifest_sha256:sha(manifest)});
 }
 const fetcher=async(url,options)=>{
  const name=new URL(url).pathname.replace('/project/data/qualification/','');calls.push({name,cache:options.cache});
  let body=options.cache!=='no-store'?cache.get(name):undefined;
  if(body===undefined){body=name==='current.json'?pointers[current]:files.get(name);cache.set(name,body);}
  return {ok:body!==undefined,status:body===undefined?404:200,text:async()=>body};
 };
 const window={fetch:fetcher},document={baseURI:'https://fixture.invalid/project/research.html'};
 vm.runInNewContext(fs.readFileSync('fireatlas/static/qualification-data.js','utf8'),{window,document,URL,AbortSignal,crypto:webcrypto,TextEncoder});
 const first=await window.FireAtlasQualification.read('readiness.json',fetcher);assert.equal(first.value.release,'a');current='b';
 const second=await window.FireAtlasQualification.read('readiness.json',fetcher);assert.equal(second.value.release,'b');assert.match(second.url,/\/project\/data\/qualification\/releases\/b{64}\/readiness.json$/);
 assert.deepEqual(calls.filter(c=>c.name==='current.json').map(c=>c.cache),['no-store','no-store']);
 files.set('releases/'+current.repeat(64)+'/readiness.json','{"tampered":true}');cache.clear();
 await assert.rejects(window.FireAtlasQualification.read('readiness.json',fetcher),/Evidence bytes differ/);
});

test('analytical pages request source-matching qualification assets instead of stale cached scripts',()=>{
  const crypto=require('node:crypto');
  for(const file of ['qualification.js','qualification-data.js','qualification.css']){
    const version=crypto.createHash('sha256').update(fs.readFileSync('fireatlas/static/'+file)).digest('hex').slice(0,16);
    for(const page of ['research.html','evidence.html','investigate.html']){
      const html=fs.readFileSync('fireatlas/static/'+page,'utf8');
      assert.ok(html.includes('./'+file+'?v='+version+'"'),page+' must load the matching '+file+' revision');
    }
  }
});
