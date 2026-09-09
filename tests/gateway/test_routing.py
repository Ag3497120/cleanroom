import asyncio
import json
import tempfile
import unittest
from unittest.mock import AsyncMock
from compute_gateway import Gateway
from compute_routing import small_pair, loopback_endpoint
from gateway_policy import Refused


def model(name, size, digest=None):
    return dict(name=name,parameters=size*1e9 if size else None,digest=digest or name,provider='ollama')

class Routing(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.g=Gateway(dict(site_url='https://site.example/',gateway_url='https://api.example',
                            state_dir=self.tmp.name,owner_github_id='1',secondary_ollama='http://127.0.0.1:11435'))
        self.g.identity=lambda r:dict(subject=r.subject,login='fixture')
        self.catalog=[model('large',36),model('small',2),model('medium',7)]
        self.g.inventory=AsyncMock(return_value=self.catalog)
        self.g.approve_dialog=AsyncMock(side_effect=self.approve)
        self.g.execute=AsyncMock(side_effect=self.execute)
        self.permission=asyncio.Event();self.finish=asyncio.Event()
    async def approve(self, job):
        await self.permission.wait();return True
    async def execute(self, job):
        await self.finish.wait();return {'answer':'fixture'}
    async def asyncTearDown(self):
        for t in list(self.g.tasks):t.cancel()
        await asyncio.gather(*self.g.tasks,return_exceptions=True)
        self.g.store.db.close();self.g.lock.close();self.tmp.cleanup()
    async def submit(self,subject,key=None):
        class Request:
            async def json(inner):return dict(request='fixture request',locale='ja',inspection='small',implementation='large',key=key or subject*16)
        r=Request();r.subject=subject
        return json.loads((await self.g.submit(r)).text)
    async def test_two_nodes_then_busy_without_quota(self):
        first,second=await asyncio.gather(self.submit('1'),self.submit('2'))
        self.assertEqual(first['compute']['node'],'primary')
        self.assertEqual(second['compute']['node'],'backup-24GB')
        self.assertEqual(second['compute']['implementation'],'medium')
        self.assertEqual(second['compute']['inspection'],'small')
        self.assertEqual(self.g.store.db.execute('select count(*) from uses').fetchone()[0],0)
        with self.assertRaisesRegex(Refused,'COMPUTE_BUSY'):await self.submit('3')
        repeat=await self.submit('2')
        self.assertEqual(repeat['id'],second['id'])
        self.permission.set()
        for _ in range(5):await asyncio.sleep(0)
        self.assertEqual(self.g.store.get(first['id'])['status'],'RUNNING')
        self.assertEqual(self.g.store.get(second['id'])['status'],'RUNNING')
        self.assertEqual(self.g.adapter_profile(model('small',2),'backup-24GB')['endpoint'],'http://127.0.0.1:11435/api/chat')
        self.finish.set()
        await asyncio.gather(*list(self.g.tasks))
        await asyncio.sleep(0)
        self.assertEqual(self.g.reservations,{})
    async def test_disconnected_backup_does_not_accept_job(self):
        await self.submit('1')
        self.g.inventory.side_effect=[self.catalog,Refused('OLLAMA_UNAVAILABLE')]
        with self.assertRaisesRegex(Refused,'COMPUTE_BUSY'):await self.submit('2')
        self.assertEqual(self.g.store.db.execute('select count(*) from jobs').fetchone()[0],1)
    async def test_cancel_releases_slot_without_approval(self):
        first=await self.submit('1')
        self.g.active[first['id']].cancel()
        await asyncio.gather(*list(self.g.tasks),return_exceptions=True)
        await asyncio.sleep(0)
        self.assertEqual(self.g.reservations,{})
    async def test_changed_backup_digest_prevents_execution(self):
        await self.submit('1');second=await self.submit('2')
        self.g.inventory.return_value=[model('large',36),model('small',2,'changed'),model('medium',7)]
        self.permission.set()
        await asyncio.gather(*list(self.g.tasks))
        self.assertEqual(self.g.store.get(second['id'])['result']['error'],'MODEL_CHANGED_REAPPROVE')
        self.g.execute.assert_not_awaited()
    def test_ten_b_cap_unknown_and_same_digest(self):
        with self.assertRaisesRegex(Refused,'COMPUTE_BUSY'):small_pair([model('a',7),model('b',4),model('c',None)])
        with self.assertRaisesRegex(Refused,'COMPUTE_BUSY'):small_pair([model('a',2,'same'),model('b',3,'same')])
        self.assertEqual(small_pair([model('a',7),model('b',3)])['total_parameters'],10e9)
    def test_public_endpoints_cannot_be_configured(self):
        for endpoint in ['http://10.0.0.2:11434','http://example.com:11434','http://user@127.0.0.1:11435','http://127.0.0.1:11435/path']:
            with self.assertRaises(ValueError):loopback_endpoint(endpoint)
