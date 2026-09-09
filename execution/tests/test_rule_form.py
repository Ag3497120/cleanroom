import tempfile,unittest,fnmatch
from pathlib import Path
from precedent.rule_form import draft,conditions
from precedent.policy import decide

class RuleDraft(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.folder=Path(self.tmp.name).resolve()/'repo[1]';self.folder.mkdir()
  self.values={'name':'choice','folder':str(self.folder),'all_folders':False,'event':'要望の解釈が複数ある','action':'複数案を作って比較する','when':[('count','整数','2')],'exceptions':[('locked','真偽','はい')],'evidence':'spec','examples':'two options','counterexamples':'one option','expires':''}
 def tearDown(self):self.tmp.cleanup()
 def test_draft_is_inactive_and_scope_is_literal(self):
  r=draft(**self.values);self.assertEqual(r['status'],'DRAFT');self.assertTrue(fnmatch.fnmatchcase(str(self.folder),r['scope']['repository']));self.assertFalse(fnmatch.fnmatchcase(str(self.folder).replace('[1]','1'),r['scope']['repository']))
  self.assertEqual(decide([r],str(self.folder),'AMBIGUOUS_REQUIREMENT',{'count':2,'locked':False},{'spec':True})['action'],'ESCALATE')
  r['status']='ACTIVE';self.assertEqual(decide([r],str(self.folder),'AMBIGUOUS_REQUIREMENT',{'count':2,'locked':False},{'spec':True})['action'],'FORK')
  self.assertEqual(decide([r],str(self.folder),'AMBIGUOUS_REQUIREMENT',{'count':2},{'spec':True})['action'],'DEFER')
 def test_types_and_bad_values(self):
  self.assertEqual(conditions([('none','値なし',''),('flag','真偽','いいえ'),('text','文字','2')]),{'none':None,'flag':False,'text':'2'})
  for rows in [[('a','整数','2.5')],[('a','小数','NaN')],[('a','真偽','true')],[('a','文字','x'),('a','文字','y')]]:
   with self.assertRaises(ValueError):conditions(rows)
 def test_scope_requires_deliberate_all_places_and_valid_date(self):
  self.values['folder']=''
  with self.assertRaises(ValueError):draft(**self.values)
  self.values['all_folders']=True;self.assertEqual(draft(**self.values)['scope']['repository'],'*')
  self.values['expires']='2026-02-30'
  with self.assertRaises(ValueError):draft(**self.values)
