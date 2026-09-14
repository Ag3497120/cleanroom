"""Regression for a revision-6 OWN / revision-8 DELEGATE snapshot splice.

Exercise the real catalog, ownership projection and command dispatcher with an
in-memory store seam. The second snapshot represents a concurrent committed
target selection. No files, ledgers, model adapters or network are accessed.
These tests check snapshot composition, not event validation or SQLite locking.

Original file SHA256: not applicable (new file, absent before this addition).
"""
from copy import deepcopy
from types import SimpleNamespace
from unittest import mock
import json
import unittest

from verantyx.assets import project_catalog
from verantyx.commands_response import dispatch
from verantyx.ownership_dictionary import project_ownership_dictionary


PROJECT = "00000000-0000-0000-0000-000000000001"
REQUEST_REF = PROJECT + ":00000000-0000-0000-0000-000000000001"
CANDIDATE_REF = PROJECT + ":00000000-0000-0000-0000-000000000003"
OWN_REF = PROJECT + ":00000000-0000-0000-0000-000000000005"
DELEGATE_REF = PROJECT + ":00000000-0000-0000-0000-000000000007"


class AdvancingSnapshotStore:
    """A second read observes the newer commit, reproducing the original race."""
    project_id = PROJECT

    def __init__(self, first, second=None):
        self.first = first
        self.second = first if second is None else second
        self.reads = 0

    def project_snapshot(self):
        self.reads += 1
        return deepcopy(self.first if self.reads == 1 else self.second)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class OwnershipSnapshotConsistencyTests(unittest.TestCase):
    def setUp(self):
        candidate = {
            "id": "candidate", "concept": "Retry guard", "concept_id": "retry_guard",
            "ownership_target": "OWN", "target_is_suggestion": False,
            "target_ref": OWN_REF, "source_ref": CANDIDATE_REF,
            "source_refs": [REQUEST_REF, CANDIDATE_REF], "recorded": True,
            "status": "OPEN", "evidence": [], "history": [{"source_ref": OWN_REF}],
        }
        state = {
            "project_id": PROJECT, "run_id": "first", "context": {},
            # Explicit lookup still retrieves recorded ownership choices when
            # suggestions are off; no generated template fixture is needed.
            "learning_preferences": {"mode": "off", "max_items": 3},
            "learning_candidates": {"candidate": candidate},
        }
        self.old = {"project_revision": 6, "as_of": "2026-09-10T00:00:00.000000Z",
                    "states": [state], "rules": {}, "events": []}
        self.new = deepcopy(self.old)
        self.new.update(project_revision=8, as_of="2026-09-10T00:00:01.000000Z")
        self.new["states"][0]["learning_candidates"]["candidate"].update(
            ownership_target="DELEGATE", target_ref=DELEGATE_REF,
            history=[{"source_ref": OWN_REF}, {"source_ref": DELEGATE_REF}])

    def assert_basis(self, result, snapshot):
        self.assertEqual(result["project_revision"], snapshot["project_revision"])
        self.assertEqual(result["as_of"], snapshot["as_of"])
        self.assertEqual(result["currentness"], "AS_OF_RECORDED_PROJECT_TIME")
        self.assertEqual(result["authority"], "REFERENCE_ONLY")

    def assert_choice(self, result, target, ref):
        self.assertEqual(len(result["learning"]), 1)
        row = result["learning"][0]
        self.assertEqual(row["ownership_target"], target)
        self.assertEqual(row["selected_target"], target)
        self.assertEqual(row["selection_status"], "HUMAN_SELECTED")
        self.assertFalse(row["target_is_suggestion"])
        self.assertEqual(row["target_ref"], ref)
        self.assertEqual(row["latest_learning_ref"], ref)
        self.assertEqual(row["source_ref"], CANDIDATE_REF)
        self.assertEqual(row["source_refs"], [REQUEST_REF, CANDIDATE_REF])
        self.assertEqual(row["mastery_assessment"], "NOT_ASSESSED")
        self.assertFalse(result["ownership"]["delegation_grants_authority"])

    def test_split_views_cannot_splice_revision_eight_choice_into_revision_six(self):
        for view in ("learn", "delegate"):
            with self.subTest(view=view):
                store = AdvancingSnapshotStore(self.old, self.new)
                result = project_ownership_dictionary(store, None, "en", view=view)
                self.assertEqual(store.reads, 1, "Ownership and assets must share one store snapshot")
                self.assert_basis(result, self.old)
                self.assertNotIn(DELEGATE_REF, json.dumps(result))
                if view == "learn":
                    self.assert_choice(result, "OWN", OWN_REF)
                else:
                    self.assertEqual(result["learning"], [])
                self.assertEqual(self.old["states"][0]["learning_candidates"]["candidate"]["target_ref"], OWN_REF)

    def test_fresh_lookup_can_report_revision_eight_with_matching_provenance(self):
        store = AdvancingSnapshotStore(self.new)
        result = project_ownership_dictionary(store, None, "en", view="delegate")
        self.assertEqual(store.reads, 1)
        self.assert_basis(result, self.new)
        self.assert_choice(result, "DELEGATE", DELEGATE_REF)

    def test_all_view_retains_existing_single_snapshot_catalog_contract(self):
        store = AdvancingSnapshotStore(self.old, self.new)
        result = project_ownership_dictionary(store, None, "en", query="retry_guard", view="all")
        expected = project_catalog(AdvancingSnapshotStore(self.old), None, "en", query="retry_guard")
        self.assertEqual(store.reads, 1)
        self.assertEqual(result, expected)
        self.assert_basis(result, self.old)
        self.assertEqual(result["learning"][0]["ownership_target"], "OWN")
        self.assertNotIn("view", result)
        self.assertNotIn("ownership", result)

    def test_dictionary_dispatch_preserves_one_snapshot_for_each_view(self):
        for view in ("all", "learn", "delegate"):
            with self.subTest(view=view):
                store = AdvancingSnapshotStore(self.old, self.new)
                args = SimpleNamespace(command="dictionary", run_id=None, query="retry_guard", view=view, limit=24)
                with mock.patch("verantyx.storage.sqlite.EventStore", return_value=store) as factory:
                    result = dispatch(None, {"project": {"id": PROJECT}}, args, "en")
                factory.assert_called_once_with(None, PROJECT)
                self.assertEqual(store.reads, 1)
                self.assertTrue(result["ok"])
                self.assertEqual(result["command"], "dictionary")
                self.assert_basis(result["catalog"], self.old)
                self.assertNotIn(DELEGATE_REF, json.dumps(result))
                if view == "learn":
                    self.assert_choice(result["catalog"], "OWN", OWN_REF)
                elif view == "delegate":
                    self.assertEqual(result["catalog"]["learning"], [])
                else:
                    self.assertEqual(result["catalog"]["learning"][0]["ownership_target"], "OWN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
