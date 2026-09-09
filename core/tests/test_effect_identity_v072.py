"""A renamed permission question cannot replay an uncertain identical effect."""
from test_constitution import Fixture, proposal, PRECEDENT
from verantyx.effects import authorize, execute
from verantyx.errors import LedgerError


class EffectIdentityTests(Fixture):
    def test_renamed_point_cannot_reauthorize_the_same_uncertain_effect(self):
        self.init_git()
        self.promote()
        self.run_task('candidate', proposal('candidate', action=True))
        original = authorize(self.root, self.cfg, 'candidate', 'writer', PRECEDENT,
                             'first-permit', clock=self.clock)
        def crash(stage):
            if stage == 'after_effect':
                raise RuntimeError('Artificial interruption after actual first effect')
        with self.assertRaises(RuntimeError):
            execute(self.root, self.cfg, 'candidate', original['lease_id'], PRECEDENT,
                    'first-execute', clock=self.clock, fault=crash)
        unknown = execute(self.root, self.cfg, 'candidate', original['lease_id'], PRECEDENT,
                          'first-execute', clock=self.clock)
        self.assertEqual(unknown['execution']['status'], 'OUTCOME_UNKNOWN')
        renamed = proposal('candidate', revision=unknown['recorded_revision'], action=True)
        renamed['decision_points'][0]['id'] = 'same-choice-renamed'
        renamed['actions'][0]['arguments']['point_id'] = 'same-choice-renamed'
        self.run_task('candidate', renamed, resume=True)
        with self.assertRaises(LedgerError) as error:
            authorize(self.root, self.cfg, 'candidate', 'writer', PRECEDENT,
                      'second-permit', clock=self.clock)
        self.assertEqual(error.exception.code, 'EXECUTION_OUTCOME_UNKNOWN')

    def test_a_different_concrete_candidate_stays_available(self):
        self.init_git()
        self.promote()
        self.run_task('candidate', proposal('candidate', action=True))
        original = authorize(self.root, self.cfg, 'candidate', 'writer', PRECEDENT,
                             'first-permit', clock=self.clock)
        def crash(stage):
            if stage == 'after_effect':
                raise RuntimeError('Artificial interruption after actual first effect')
        with self.assertRaises(RuntimeError):
            execute(self.root, self.cfg, 'candidate', original['lease_id'], PRECEDENT,
                    'first-execute', clock=self.clock, fault=crash)
        unknown = execute(self.root, self.cfg, 'candidate', original['lease_id'], PRECEDENT,
                          'first-execute', clock=self.clock)
        revised = proposal('candidate', revision=unknown['recorded_revision'], action=True)
        revised['actions'][0]['arguments']['files']['calc.py'] = 'def add(a, b):\n    return (a + b)\n'
        self.run_task('candidate', revised, resume=True)
        permission = authorize(self.root, self.cfg, 'candidate', 'writer', PRECEDENT,
                               'changed-candidate', clock=self.clock)
        result = execute(self.root, self.cfg, 'candidate', permission['lease_id'], PRECEDENT,
                         'changed-execute', clock=self.clock)
        self.assertEqual(result['execution']['receipt']['verification']['closure'], 'BOUNDED')
        self.assertEqual(len(result['state']['effects']), 2)
