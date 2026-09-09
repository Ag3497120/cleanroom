import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from precedent.store import Store
from precedent.attention import Recorder,summary

class Attention(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name));self.store.run('r',{'usage':{'local_calls':2}});self.store.run('other',{});self.recorder=Recorder()
 def tearDown(self):self.store.close();self.tmp.cleanup()
 def test_explicit_interval_monotonic_time_and_no_budget_changes(self):
  with patch('precedent.attention.time.monotonic',return_value=100),patch('precedent.attention.time.time',return_value=1000):row=self.recorder.start(self.store,'r','review')
  self.assertIsNone(summary(self.store,'r')['completed_elapsed_seconds'])
  with patch('precedent.attention.time.monotonic',return_value=105),patch('precedent.attention.time.time',return_value=500):self.recorder.close(self.store,'r',row['interval'])
  body=summary(self.store,'r');self.assertEqual(body['completed_elapsed_seconds'],5);self.assertEqual(body['by_category']['review'],5);self.assertEqual(self.store.run('r')['usage']['local_calls'],2)
  with self.assertRaises(ValueError):self.recorder.close(self.store,'r',row['interval'])
 def test_restart_keeps_unknown_interval_and_requires_explicit_abandonment(self):
  row=self.recorder.start(self.store,'r','rework');new=Recorder()
  with self.assertRaises(ValueError):new.close(self.store,'r',row['interval'])
  self.assertEqual(summary(self.store,'r')['unfinished_count'],1)
  new.close(self.store,'r',row['interval'],abandon=True);body=summary(self.store,'r');self.assertEqual(body['abandoned_count'],1);self.assertIsNone(body['completed_elapsed_seconds']);self.assertIsNone(body['intervals'][0]['seconds'])
  new.start(self.store,'r','decision')
 def test_overlapping_runs_and_wrong_run_closure_rejected(self):
  row=self.recorder.start(self.store,'r','review')
  with self.assertRaises(ValueError):Recorder().start(self.store,'other','review')
  with self.assertRaises(ValueError):self.recorder.close(self.store,'other',row['interval'],True)
  with self.assertRaises(ValueError):self.recorder.start(self.store,'missing','review')
  with self.assertRaises(ValueError):self.recorder.start(self.store,'r','unsupported')
  self.assertEqual(summary(self.store,'r')['unfinished_count'],1)
