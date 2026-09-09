"""Independent regressions from the governance-to-verifier handoff audit."""
from copy import deepcopy
from datetime import timedelta
import base64
import hashlib
import json
from unittest import mock
import unittest

import test_verification as verification_fixtures
from verantyx.application import record_run
from verantyx.domain.codec import digest
from verantyx.domain.verification import MAX_INPUT
from verantyx.errors import LedgerError
from verantyx.kernel.reducer import replay
from verantyx.verification import engine_identity


class VerificationAuditTests(unittest.TestCase):
    setUp = verification_fixtures.VerificationTests.setUp
    tearDown = verification_fixtures.VerificationTests.tearDown
    plan = verification_fixtures.VerificationTests.plan
    run_check = verification_fixtures.VerificationTests.run_check
    events = verification_fixtures.VerificationTests.events

    def replace_proposal(self, statement):
        state = replay(self.events())
        proposal = deepcopy(state['proposal'])
        proposal['context_revision'] = state['revision']
        proposal['claims'][0]['statement'] = statement
        (self.root / 'proposal.json').write_text(json.dumps(proposal))
        return record_run(self.root, self.cfg, run_id='verify', resume=True, proposal_path=self.root / 'proposal.json', clock=self.clock)

    def test_true_and_one_receipts_are_distinct_even_with_a_recomputed_event_hash(self):
        self.run_check(self.plan()['verification_id'])
        events = self.events()
        index = next(i for i, event in enumerate(events) if event['type'] == 'VerificationRecorded')
        for replacement in (1, 1.0):
            forged = deepcopy(events[index])
            forged['payload']['result']['checks'][0]['passed'] = replacement
            forged['event_hash'] = digest({key: value for key, value in forged.items() if key != 'event_hash'})
            with self.subTest(replacement=replacement):
                with self.assertRaises(LedgerError) as error:
                    replay([*events[:index], forged])
                self.assertEqual(error.exception.code, 'VERIFICATION_RECEIPT_INVALID')

    def test_reproduction_rejects_a_changed_boolean_expected_value_contract(self):
        spec = deepcopy(self.spec)
        spec['checks'][0].update(pointer='/ok', expected=True)
        first = self.plan(spec)['verification_id']
        self.run_check(first)
        changed = deepcopy(spec)
        changed.update(method='REPRODUCTION', reproduces=first)
        changed['checks'][0]['expected'] = 1
        with self.assertRaises(LedgerError):
            self.plan(changed, key='typed-contract-change')

    def test_unrelated_predicate_success_does_not_close_arbitrary_prose(self):
        self.replace_proposal('This program is mathematically proved correct for every input and needs no human approval.')
        spec = deepcopy(self.spec)
        spec['property'] = 'The selected file has this byte count.'
        spec['checks'] = [{'id': 'size', 'kind': 'bytes.size', 'pointer': '', 'expected': len((self.root / 'report.json').read_bytes())}]
        result = self.run_check(self.plan(spec)['verification_id'])
        claim = result['state']['assessment']['claims'][0]
        self.assertEqual((claim['status'], claim['epistemic_status'], claim['verification'], claim['closure']),
                         ('UNKNOWN', 'UNKNOWN', 'UNVERIFIED', 'UNKNOWN'))
        self.assertEqual(claim['property_evidence']['closure'], 'BOUNDED')
        self.assertEqual(claim['property_evidence']['epistemic_status'], 'SUPPORTED')
        self.assertEqual(claim['property_evidence']['scope'], 'FIXED_TARGET_AND_PREDICATES_ONLY')
        self.assertTrue(claim['property_evidence']['current_evidence_refs'])
        self.assertEqual(claim['prose_entailment'], 'NOT_ASSESSED')
        self.assertEqual(result['state']['assessment']['evidence'], 'UNKNOWN')
        self.assertTrue(any(gap['code'] == 'CLAIM_NOT_VERIFIED' for gap in result['state']['assessment']['gaps']))
        self.assertFalse(result['state']['can_execute_effects'])

    def test_unrelated_predicate_failure_does_not_refute_arbitrary_prose(self):
        self.replace_proposal('A separate value decision should be made by a human.')
        spec = deepcopy(self.spec)
        spec['checks'][0]['expected'] = -1
        result = self.run_check(self.plan(spec)['verification_id'])
        claim = result['state']['assessment']['claims'][0]
        self.assertEqual(claim['epistemic_status'], 'UNKNOWN')
        self.assertEqual(claim['property_evidence']['epistemic_status'], 'REFUTED')
        self.assertEqual(claim['property_evidence']['closure'], 'REFUTED')
        self.assertEqual(result['verification']['receipt']['result']['checks'][0]['passed'], False)

    def test_64k_input_is_sealed_and_oversized_input_is_rejected_without_a_plan(self):
        raw = b'x' * MAX_INPUT
        (self.root / 'report.json').write_bytes(raw)
        record_run(self.root, self.cfg, run_id='verify', resume=True, clock=self.clock)
        spec = deepcopy(self.spec)
        spec['checks'] = [{'id': 'hash', 'kind': 'bytes.sha256', 'pointer': '', 'expected': hashlib.sha256(raw).hexdigest()}]
        result = self.run_check(self.plan(spec)['verification_id'])
        receipt = result['verification']['receipt']
        self.assertEqual(base64.b64decode(receipt['input_base64']), raw)
        self.assertEqual(receipt['input_sha256'], hashlib.sha256(raw).hexdigest())
        (self.root / 'report.json').write_bytes(raw + b'x')
        record_run(self.root, self.cfg, run_id='verify', resume=True, clock=self.clock)
        before = self.events()
        with self.assertRaises(LedgerError) as error:
            self.plan(spec, key='oversized')
        self.assertEqual(error.exception.code, 'VERIFICATION_INPUT_LIMIT')
        self.assertEqual(self.events(), before)

    def test_engine_change_during_check_invalidates_the_receipt(self):
        identifier = self.plan()['verification_id']
        original = engine_identity()
        changed = {**original, 'source_sha256': '0' * 64}
        with mock.patch('verantyx.verification.engine_identity', side_effect=[original, changed]):
            result = self.run_check(identifier)
        self.assertEqual(result['verification']['receipt']['reason'], 'ENGINE_CHANGED')
        self.assertEqual(result['verification']['status'], 'INVALIDATED')
        self.assertIsNone(result['verification']['receipt']['result'])

    def test_negative_controls_cannot_launder_integer_rejected_flags(self):
        spec = deepcopy(self.spec)
        spec.update(method='NEGATIVE_CONTROL', negative_controls=[{'id': 'no', 'input_base64': base64.b64encode(b'{"answer":0}').decode()}])
        self.run_check(self.plan(spec)['verification_id'])
        events = self.events()
        index = next(i for i, event in enumerate(events) if event['type'] == 'VerificationRecorded')
        forged = deepcopy(events[index])
        forged['payload']['result']['negative_controls'][0]['rejected'] = 1
        forged['event_hash'] = digest({key: value for key, value in forged.items() if key != 'event_hash'})
        with self.assertRaises(LedgerError) as error:
            replay([*events[:index], forged])
        self.assertEqual(error.exception.code, 'VERIFICATION_RECEIPT_INVALID')

    def test_reproduction_cannot_drop_failed_negative_controls(self):
        spec = deepcopy(self.spec)
        spec.update(method='NEGATIVE_CONTROL', negative_controls=[{'id': 'bad-control', 'input_base64': base64.b64encode(b'{"answer":42}').decode()}])
        first = self.plan(spec)['verification_id']
        initial = self.run_check(first)
        self.assertEqual(initial['verification']['receipt']['result']['closure'], 'CONTESTED')
        changed = deepcopy(spec)
        changed.update(method='REPRODUCTION', reproduces=first, negative_controls=[])
        with self.assertRaises(LedgerError):
            self.plan(changed, key='dropped-controls')
        changed['negative_controls'] = deepcopy(spec['negative_controls'])
        result = self.run_check(self.plan(changed, key='repeat-controls')['verification_id'], key='reproduction-check')
        evidence = result['verification']['receipt']['result']
        self.assertTrue(evidence['reproduction_match'])
        self.assertEqual(evidence['closure'], 'CONTESTED')
        self.assertFalse(evidence['negative_controls'][0]['rejected'])


if __name__ == '__main__':
    unittest.main()
