"""Copy the two local backup models over the established Thunderbolt SSH tunnel."""
import asyncio
import hashlib
import json
from pathlib import Path
import aiohttp

async def main():
    root=Path.home()/'.ollama/models'
    endpoint='http://127.0.0.1:11435'
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800)) as client:
        for family,tag in [('qwen3.5','2b'),('qwen2.5','3b')]:
            name=family+':'+tag
            manifest=json.loads((root/'manifests/registry.ollama.ai/library'/family/tag).read_text())
            def blob(digest):return root/'blobs'/digest.replace(':','-')
            config=json.loads(blob(manifest['config']['digest']).read_text())
            body={'model':name,'files':{},'stream':False}
            for key in ('renderer','parser'):
                if config.get(key):body[key]=config[key]
            for layer in manifest['layers']:
                kind=layer['mediaType'].removeprefix('application/vnd.ollama.image.')
                path=blob(layer['digest'])
                if kind=='model':
                    with path.open('rb') as f:
                        if 'sha256:'+hashlib.file_digest(f,'sha256').hexdigest()!=layer['digest']:raise RuntimeError('Local digest mismatch')
                    async with client.head(endpoint+'/api/blobs/'+layer['digest']) as r:exists=r.status==200
                    if not exists:
                        print('Transferring',name,path.stat().st_size,'bytes',flush=True)
                        with path.open('rb') as f:
                            async with client.post(endpoint+'/api/blobs/'+layer['digest'],data=f,headers={'Content-Type':'application/octet-stream'}) as r:
                                if r.status!=201:raise RuntimeError(await r.text())
                    body['files']['model.gguf']=layer['digest']
                elif kind in ('template','system','license'):body[kind]=path.read_text()
                elif kind=='params':body['parameters']=json.loads(path.read_text())
                else:raise RuntimeError('Unsupported layer: '+kind)
            async with client.post(endpoint+'/api/create',json=body) as r:
                data=await r.json()
                if r.status!=200 or data.get('status')!='success':raise RuntimeError(data)
            print('Copied',name,flush=True)
        async with client.get(endpoint+'/api/tags') as r:
            for m in (await r.json())['models']:print(m['name'],m['details']['parameter_size'],flush=True)
if __name__=='__main__':asyncio.run(main())
