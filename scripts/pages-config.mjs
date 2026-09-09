import { writeFileSync, cpSync, mkdirSync, existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
const url = process.env.COMPUTE_GATEWAY_URL ?? '';
if (!url && process.env.ALLOW_UNCONFIGURED_COMPUTE !== 'true') throw new Error('Set COMPUTE_GATEWAY_URL or explicitly allow an unconnected terminal.');
const parsed = url ? new URL(url) : null;
if (parsed && (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash)) throw new Error('Expected an HTTPS origin, not a URL with credentials or a path.');
const base=process.env.PAGES_BASE_PATH??'';
if(base && !/^\/[A-Za-z0-9._-]+$/.test(base))throw new Error('Invalid GitHub Pages base path');
const source=resolve('dist/client'+base);
const entry=base?resolve('dist/client'+base+'.html'):resolve(source,'index.html');
if(!existsSync(entry))throw new Error('Build with the same PAGES_BASE_PATH before packaging.');
// vinext exports /repo.html and /repo/assets. GitHub Pages mounts the
// uploaded artifact at /repo/, so remove that extra filesystem nesting.
rmSync('dist/pages',{recursive:true,force:true});mkdirSync('dist/pages',{recursive:true});
cpSync(source,'dist/pages',{recursive:true});cpSync(entry,'dist/pages/index.html');
if(existsSync('dist/client/404.html'))cpSync('dist/client/404.html','dist/pages/404.html');
writeFileSync('dist/pages/compute-config.json', JSON.stringify({public_mode:true,gateway_url:parsed?.origin??''})+'\n');
writeFileSync('dist/pages/.nojekyll','');
