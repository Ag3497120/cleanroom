"""Independent bounded audit of the connections copy; no real keys or network."""
from pathlib import Path
from copy import deepcopy
from unittest import mock
import io,json,os,sys,unittest,tempfile
from datetime import datetime,timezone

SOURCE = Path(os.environ.get('VERANTYX_AUDIT_SOURCE', str(Path(__file__).resolve().parents[1] / 'src'))).resolve()
sys.path.insert(0, str(SOURCE))
from verantyx.domain.codec import canonical
from verantyx.errors import LedgerError
from verantyx.model_api import request,FORMAT
from verantyx.learning_external import validate_response

class Response:
    status=200
    def __init__(self,raw): self.stream=io.BytesIO(raw)
    def getheader(self,name,default=None):
        return {'Content-Type':'application/json','Content-Length':str(len(self.stream.getvalue()))}.get(name,default)
    def read1(self,size): return self.stream.read(size)
class Connection:
    sock=None
    def __init__(self,response): self.response=response; self.calls=0
    def request(self,*args): self.calls+=1
    def getresponse(self): return self.response
    def close(self): pass

class ConnectionAuditTests(unittest.TestCase):
    def request_echo(self,secret):
        proposal={'schema_version':1,'task_id':'audit','context_revision':1,'response_locale':'ja','summary':secret,'claims':[],'actions':[],'unknowns':[]}
        envelope={'object':'response','status':'completed','incomplete_details':None,'output':[{'type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':canonical(proposal)}]}]}
        connection=Connection(Response(canonical(envelope).encode()))
        config={'format':FORMAT,'provider':'openai','model':'fixture','endpoint':'http://127.0.0.1:1/v1/responses','key_env':'VERANTYX_AUDIT_FAKE_KEY','allow_loopback_http':True,'timeout':2,'max_output_tokens':1000,'max_response_bytes':65536}
        value={'format':'verantyx.proposal-request.v1','task':{'task_id':'audit','context_revision':1}}
        with mock.patch.dict(os.environ,{'VERANTYX_AUDIT_FAKE_KEY':secret}),mock.patch('verantyx.model_api.http.client.HTTPConnection',return_value=connection):
            return request(config,value)
    def test_plain_credential_echo_is_rejected(self):
        with self.assertRaises(LedgerError): self.request_echo('synthetic-plain-secret')
    def test_json_escaped_credential_echo_is_rejected(self):
        with self.assertRaises(LedgerError): self.request_echo('synthetic-quote"slash\\secret')
    def test_learning_fixed_scope_fields_cannot_change(self):
        template={'schema_version':1,'kind':'MATERIAL_PROPOSAL','candidate_id':'candidate','candidate_hash':'a'*64,'cycle':1,'scope':'SELECTED_CANDIDATE_ONLY','source_refs':['one'],'limitations':['review only'],'content':{'title':'T','principle':'P','worked_example':'E','counterexample':'C','check':'Q'}}
        value={'format':'verantyx.learning-request.v1','operation':'material','response_template':template}
        for update in ({'cycle':True},{'scope':'ALL_CONCEPTS'},{'mastery':'MASTERED'},{'source_refs':[]}):
            bad={**deepcopy(template),**update}
            with self.subTest(update=update),self.assertRaises(LedgerError): validate_response(bad,value)

class LearningAuditTests(unittest.TestCase):
    def test_supported_external_answer_never_becomes_mastery_or_permission_and_is_not_resent(self):
        from verantyx import config
        from verantyx.application import record_run
        from verantyx.learning import control_learning,project_learning
        from verantyx.learning_external import generate
        from verantyx.storage.sqlite import EventStore,parse_archive
        from verantyx.kernel.reducer import replay
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary).resolve(); cfg=config.defaults(root,'ja'); config.save(root,cfg,None)
            moment=datetime(2026,9,6,tzinfo=timezone.utc); clock=lambda:moment
            first=record_run(root,cfg,request='isolated audit',run_id='learn',clock=clock)
            proposal={'schema_version':1,'task_id':'learn','context_revision':first['state']['revision'],'response_locale':'ja','summary':'synthetic audit','claims':[],'actions':[],'unknowns':[]}
            path=root/'proposal.json'; path.write_text(json.dumps(proposal)); record_run(root,cfg,run_id='learn',resume=True,proposal_path=path,clock=clock)
            raised=control_learning(root,cfg,'learn','raise',key='raise',clock=clock,candidate_id='test',concept_id='test',concept='bounded claims',why_now=['audit'],minimum_model='separate authority',counterexample='approval is not evidence',check='explain',source_refs=[first['state']['request_ref']])
            answered=control_learning(root,cfg,'learn','explain',key='answer',clock=clock,candidate_id='test',statement='synthetic submitted answer')
            source=answered['state']['learning_candidates']['test']['evidence'][-1]['source_ref']; revision=answered['state']['revision']
            program=root/'generator.py'
            program.write_text("import json,sys\nfrom pathlib import Path\nr=json.load(sys.stdin); p=r['response_template']; p['assessment']='SUPPORTED'; p['content']='Synthetic evaluator claims mastery; this is untrusted prose.'\nwith Path("+repr(str(root/'calls'))+").open('a') as h: h.write('call\\n')\nprint(json.dumps(p))\n")
            adapter=root/'adapter.json'; adapter.write_text(json.dumps({'argv':[sys.executable,str(program)]}))
            args=dict(candidate_id='test',operation='assess',adapter_path=adapter,key='external',expected_revision=revision,submission_ref=source,rubric='fixed synthetic rubric',clock=clock)
            result=generate(root,cfg,'learn',**args)
            self.assertEqual(result['external_result']['assessment'],'SUPPORTED')
            learner=project_learning(result['state'])[0]
            self.assertEqual(learner['mastery_assessment'],'NOT_ASSESSED'); self.assertFalse(learner['externally_verified'])
            again=generate(root,cfg,'learn',**args)
            self.assertEqual((root/'calls').read_text(),'call\n')
            self.assertFalse(again['external_call_repeated'])
            with EventStore(root,cfg['project']['id']) as store:
                events=store.events('learn'); raw=store.export().encode()
            self.assertFalse({'HumanDecisionRecorded','EffectAuthorized'} & {e['type'] for e in events})
            with mock.patch('verantyx.learning_external.generate',side_effect=AssertionError('replay invoked model')):
                self.assertEqual(replay(events)['learning_candidates'],result['state']['learning_candidates']); parse_archive(raw)

if __name__=='__main__': unittest.main(verbosity=2)
