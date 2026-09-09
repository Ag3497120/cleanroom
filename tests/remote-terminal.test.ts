import assert from 'node:assert/strict';
import { test } from 'node:test';
import headless from '@xterm/headless';
import type { Terminal } from '@xterm/xterm';
import { remoteTerminal } from '../lib/remote-terminal.ts';

void test('public terminal selects installed models, rejects over 40B and submits multiline text after login', async () => {
  const originalFetch=globalThis.fetch;
  const oldDocument=Object.getOwnPropertyDescriptor(globalThis,'document');
  Object.defineProperty(globalThis,'document',{configurable:true,value:{documentElement:{lang:'ja'}}});
  const requests: Record<string,unknown>[]=[];
  const models=[{name:'small',parameters:2.3e9,digest:'a',provider:'ollama'},
    {name:'large',parameters:36e9,digest:'b',provider:'ollama'},
    {name:'second-large',parameters:36e9,digest:'c',provider:'ollama'},
    {name:'unknown',parameters:null,digest:'d',provider:'ollama'}];
  globalThis.fetch=async (url,init) => {
    assert.equal(typeof url,'string');
    const path=url as string;
    let body:unknown={};
    if(path.endsWith('/v1/models'))body={models:structuredClone(models),spark:{available:false},identity:null};
    else if(path.endsWith('/login/start'))body={flow:'fixture',code:'ABCD',url:'https://github.com/login/device',interval:0};
    else if(path.endsWith('/login/poll'))body={token:'fixture-token',login:'fixture'};
    else if(path.endsWith('/v1/jobs')){assert.equal(typeof init?.body,'string');requests.push(JSON.parse(init?.body as string));body={id:'job-fixture',status:'PENDING'};}
    else body={status:'SUCCEEDED',result:{answer:'回答',proposed_files:{'hello.txt':'hello'},learning:[],reuse:[]}};
    return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
  };
  const term=new headless.Terminal({cols:120,rows:60,scrollback:500,allowProposedApi:true});
  const remote=remoteTerminal(term as unknown as Terminal,'https://compute.example',()=>{});
  const settle=async()=>{for(let i=0;i<12;i++){await new Promise(resolve=>setTimeout(resolve,1));await new Promise<void>(resolve=>term.write('',resolve));}};
  const screen=()=>Array.from({length:term.buffer.active.length},(_,i)=>term.buffer.active.getLine(i)?.translateToString(true)??'').join('\n');
  try {
    await settle();remote.input('/model inspection 2\r/model implementation 3\r');await settle();
    assert.match(screen(),/40B limit/);
    remote.input('/model implementation 4\r');await settle();assert.match(screen(),/選択不可/);
    remote.input('/model inspection 1\r/model implementation 2\r/lang en\r');await settle();
    assert.match(screen(),/GitHub sign-in/);
    remote.input('/login\r');await settle();
    remote.input('\x1b[200~First line\n二行目\x1b[201~');await settle();
    assert.equal(requests.length,0);
    remote.input('\r');await settle();
    assert.equal(requests.length,1);
    assert.equal(requests[0].request,'First line\n二行目');
    assert.equal(requests[0].locale,'en');
    assert.equal(requests[0].inspection,'small');
    assert.equal(requests[0].implementation,'large');
    assert.match(screen(),/hello.txt/);
    assert.match(screen(),/Nothing has been adopted/);
  } finally {
    remote.dispose();term.dispose();globalThis.fetch=originalFetch;
    if(oldDocument)Object.defineProperty(globalThis,'document',oldDocument);else Reflect.deleteProperty(globalThis,'document');
  }
});
