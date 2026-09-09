import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
const base=process.env.PAGES_BASE_PATH??'';
const html=readFileSync('dist/pages/index.html','utf8');
const config=JSON.parse(readFileSync('dist/pages/compute-config.json','utf8'));
assert.equal(config.public_mode,true);
if(config.gateway_url)assert.equal(new URL(config.gateway_url).protocol,'https:');
else assert.equal(process.env.ALLOW_UNCONFIGURED_COMPUTE,'true');
let assets=0;
for(const match of html.matchAll(/(?:src|href)="(\/[^"?#]+)"/g)){
  const url=match[1];
  assert.ok(url.startsWith(base+'/'),`Asset escaped Pages base: ${url}`);
  assert.ok(existsSync('dist/pages'+url.slice(base.length)),`Missing static asset: ${url}`);
  assets++;
}
assert.ok(assets>2,'Expected terminal scripts and styles');
assert.ok(existsSync('dist/pages/.nojekyll'));
console.log(JSON.stringify({base,assets,static_export:true}));
