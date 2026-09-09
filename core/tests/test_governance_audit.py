"""Independent final checks for scope-evidence and successor transitions."""
from copy import deepcopy
from datetime import timedelta
from unittest import mock
import unittest
import uuid

import test_governance_extended as fixture
from verantyx.application import iso
from verantyx.domain.codec import digest
from verantyx.domain.events import make_event, validate_event
from verantyx.domain.rule_extensions import validate_shadow
from verantyx.errors import LedgerError
from verantyx.kernel.rules import catalog
from verantyx.storage.sqlite import EventStore


class GovernanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixture.ExtendedFixture()
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def test_exact_and_finite_receipts_cannot_claim_independent_design_or_shared_origin_changes(self):
        f = self.fx
        rule = f.draft()
        policy = f.finite(rule)
        scope = f.report(rule)["rule"]["scope"]
        for finite in (False, True):
            original = f.backend.shadow_policy_check(policy) if finite else f.backend.shadow_check(scope)
            def validate(check):
                if finite:
                    validate_shadow(policy, check)
                else:
                    with EventStore(f.root, f.cfg["project"]["id"]) as store:
                        previous = store.events("first")[-1]
                    make_event(f.cfg["project"]["id"], "first", previous["revision"] + 1, str(uuid.uuid4()), iso(f.time),
                               "RuleShadowed", {"rule_id": rule, "check": check}, str(uuid.uuid4()), previous)
            validate(original)
            mutations = [lambda c: c["origin"].update(kind="I5", independent_design=True),
                         lambda c: c["origin"].update(independent_design=0),
                         lambda c: c["independence"]["oracle"].update(same_expected_value_source=False),
                         lambda c: c["independence"]["generator"].update(same_provider=False),
                         lambda c: c["independence"]["implementation"].update(shared_dependency=False),
                         lambda c: c["independence"]["environment"].update(same_machine=False),
                         lambda c: c["identity"].update(backend="unregistered-verifier")]
            for mutation in mutations:
                forged = deepcopy(original)
                mutation(forged)
                with self.subTest(finite=finite, mutation=mutation), self.assertRaises(LedgerError):
                    validate(forged)

    def test_withdrawn_contested_and_expired_successors_cannot_retire_current_rule(self):
        f = self.fx
        old, _ = f.promote()
        case = f.command("rule-amend", old, choice="shared", reason="Synthetic changed decision")["precedent_id"]
        f.command("precedent-accept", case)
        new = f.command("rule-draft", case)["rule_id"]
        f.command("rule-shadow", new)
        f.command("rule-confirm", new)
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            events = store.events()
            previous = store.events("first")[-1]
        for kind in ("RuleRetired", "RuleContested", "expired"):
            changed = list(events)
            tail = previous
            at = f.time
            if kind == "expired":
                at += timedelta(days=31)
            else:
                tail = make_event(f.cfg["project"]["id"], "first", tail["revision"] + 1, str(uuid.uuid4()), iso(at), kind,
                                  {"rule_id": new, "reason": "Synthetic withdrawn/contested successor"}, str(uuid.uuid4()), tail)
                changed.append(tail)
            event = make_event(f.cfg["project"]["id"], "first", tail["revision"] + 1, str(uuid.uuid4()), iso(at),
                               "RuleSuperseded", {"rule_id": old, "successor": new}, str(uuid.uuid4()), tail)
            with self.subTest(kind=kind), self.assertRaises(LedgerError):
                catalog([*changed, event])
        self.assertEqual(f.report(old)["rule"]["validity"], "CURRENT")
        f.command("rule-activate", new)
        self.assertEqual(f.report(old)["rule"]["validity"], "SUPERSEDED")

    def test_shadow_confirmation_cannot_count_foreign_policy_receipts(self):
        f = self.fx
        rule = f.draft()
        policy = f.finite(rule, minimum=1)
        f.accepted_policy(rule, policy)
        f.pilot("observed")
        confirmed = f.command("rule-policy-confirm", rule, expected_policy_sha256=digest(policy), reason="one actual task")
        with EventStore(f.root, f.cfg["project"]["id"]) as store:
            all_events = store.events()
        index = next(i for i, event in enumerate(all_events) if event["type"] == "RulePolicyConfirmed")
        forged = deepcopy(all_events[index])
        forged["payload"]["shadow_refs"] = [confirmed["state"]["request_ref"]]
        forged["event_hash"] = digest({key: value for key, value in forged.items() if key != "event_hash"})
        with self.assertRaises(LedgerError):
            catalog([*all_events[:index], forged])

    def test_finite_exception_receipt_cannot_be_rewritten_as_an_applicable_match(self):
        f = self.fx
        rule = f.draft()
        policy = f.finite(rule, minimum=1, exception=True)
        check = f.backend.shadow_policy_check(policy)
        rejected = next(case for case in check["cases"] if case["receipt"]["exceptions"])
        rejected["receipt"]["exceptions"] = []
        rejected["receipt"]["match"] = True
        rejected["expected"] = True
        with self.assertRaises(LedgerError):
            validate_shadow(policy, check)
