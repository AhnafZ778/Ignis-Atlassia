const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const route=fs.readFileSync('fireatlas/static/comparison-route.js','utf8');
function redirect(href){let result;vm.runInNewContext(route,{URL,location:{href,replace:v=>result=String(v)}});return new URL(result);}
const old=redirect('https://example.test/project/harmonization.html?region=punjab-haryana&protocol=nested&year=2025&switch=7&mode=raw&case=grove-2025&threshold=30');
assert.equal(old.pathname,'/project/research.html');assert.equal(old.searchParams.get('tab'),'comparison');
assert.equal(old.searchParams.get('cmp_region'),'punjab-haryana');assert.equal(old.searchParams.get('cmp_year'),'2025');assert.equal(old.searchParams.get('cmp_mode'),'raw');assert.equal(old.searchParams.get('cmp_switch'),'7');
assert.equal(old.searchParams.get('case'),null);assert.equal(old.searchParams.get('native_case'),'grove-2025');
const native=redirect('https://example.test/project/harmonization.html?case=grove-2025&threshold=60#native-case');
assert.equal(native.pathname,'/project/evidence.html');assert.equal(native.searchParams.get('tab'),'validity');assert.equal(native.searchParams.get('native_threshold'),'60');
const window={},location={search:'',href:'https://example.test/project/research.html'};
vm.runInNewContext(fs.readFileSync('fireatlas/static/workspace-context.js','utf8'),{window,location,URL,URLSearchParams,Date,Number,JSON,document:{addEventListener(){}},addEventListener(){}});
const C=window.FireAtlasContext;
const context=C.read('?case=park-2024&day=2024-07-30&cmp_region=punjab-haryana&cmp_year=2025&cmp_protocol=forward&cmp_switch=7&cmp_mode=raw&native_case=grove-2025&native_threshold=60&method_id=original-raw&result_sha256=original-result');
const restored=C.read(C.write(context));
for(const key of ['case','day','start','end','bbox','cmp_region','cmp_year','cmp_protocol','cmp_switch','cmp_mode','native_case','native_threshold','method_id','result_sha256'])assert.equal(restored[key],context[key],key);
assert.equal(restored.start,'2024-07-24');assert.equal(restored.cmp_year,'2025');assert.equal(restored.errors.length,0);
console.log('Integrated comparison: subpath bookmarks and independent experiment/native/study identity round trips passed.');
