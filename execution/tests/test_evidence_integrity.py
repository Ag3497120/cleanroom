import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.store import Store
from precedent.engine import Engine

class EvidenceIntegrity(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.e=Engine(Path(self.tmp.name));self.s=self.e.store
  self.s.run('r',{'local_model':'m','status':{'task':'pending'},'usage':{'local_calls':0},'limits':{'local_calls':2},'deadline':time.time()+60});self.s.event('first',{'run':'r','value':'日本語'});self.s.event('second',{'run':'r'})
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def corrupt(self):
  # Isolated test database only; simulate damage outside normal write APIs.
  self.s.db.execute('DROP TRIGGER immutable_ledger_update');self.s.db.execute("UPDATE ledger SET body='{}' WHERE seq=1");self.s.db.commit()
 def test_valid_chain_after_reopen_and_appending(self):
  before=self.s.verify_ledger();self.assertTrue(before['valid']);self.assertEqual(before['checked'],2)
  other=Store(self.s.home);self.assertEqual(other.verify_ledger(),before);other.event('third',{'value':3});other.close();self.assertEqual(self.s.verify_ledger()['checked'],3)
 def test_corruption_rejects_inference_and_resume_before_usage_or_state_changes(self):
  self.corrupt();before=self.s.run('r');self.assertFalse(self.s.verify_ledger()['valid'])
  with patch('precedent.engine.invoke') as invoke:
   with self.assertRaisesRegex(RuntimeError,'record 1'):self.e.model('r','ollama','test')
   with self.assertRaises(RuntimeError):self.e.execute('r')
  invoke.assert_not_called();self.assertEqual(self.s.run('r'),before)
 def test_cannot_extend_corrupt_chain_and_transaction_is_released(self):
  self.corrupt()
  with self.assertRaises(RuntimeError):self.s.event('third',{})
  self.assertFalse(self.s.db.in_transaction);self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM ledger').fetchone()[0],2)
 def test_invalid_json_and_parent_link_are_reported(self):
  self.s.db.execute('DROP TRIGGER immutable_ledger_update');self.s.db.execute("UPDATE ledger SET previous='wrong' WHERE seq=2");self.s.db.commit();self.assertEqual(self.s.verify_ledger()['issue_seq'],2)
  self.s.db.execute("UPDATE ledger SET body='not json' WHERE seq=1");self.s.db.commit();self.assertEqual(self.s.verify_ledger()['issue_seq'],1)
 def test_cli_inconsistent_evidence_returns_nonzero_with_json_diagnostic(self):
  import subprocess,sys
  self.corrupt()
  result=subprocess.run([sys.executable,'-m','precedent','--home',str(self.s.home),'verify-evidence'],capture_output=True,text=True)
  self.assertEqual(result.returncode,1);self.assertFalse(json.loads(result.stdout)['valid'])
