import tempfile,unittest
from unittest.mock import patch
from precedent.store import Store
from precedent.desktop_state import record,observations

class DesktopState(unittest.TestCase):
 def test_observation_expires_and_never_grants_transport(self):
  with tempfile.TemporaryDirectory() as home:
   s=Store(home)
   try:
    with patch('precedent.adapters.discover',return_value=[{'id':'claude-desktop','bundle_id':'claude'}]):r=record(s,'claude-desktop','chat','claude','auth_required','Sign in visible',source='cua')
    fresh=observations(s,'claude-desktop','claude',r['observed_at'])[0];self.assertEqual(fresh['effective_status'],'auth_required');self.assertFalse(fresh['automatic_inference'])
    self.assertEqual(observations(s,'claude-desktop','claude',r['expires_at'])[0]['effective_status'],'stale')
    self.assertEqual(observations(s,'claude-desktop','different',r['observed_at'])[0]['effective_status'],'identity_changed')
   finally:s.close()
 def test_wrong_identity_and_invented_ready_state_rejected(self):
  with tempfile.TemporaryDirectory() as home:
   s=Store(home)
   try:
    with patch('precedent.adapters.discover',return_value=[{'id':'claude-desktop','bundle_id':'claude'}]):
     with self.assertRaises(ValueError):record(s,'claude-desktop','chat','other','auth_required','Sign in visible')
     with self.assertRaises(ValueError):record(s,'claude-desktop','chat','claude','ready','Available')
   finally:s.close()
