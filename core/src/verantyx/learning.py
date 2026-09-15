"""Voluntary learning records in the existing project event ledger.

Recorded submissions describe what a local operator reports. They never certify
understanding, grant execution rights, or change a project decision.
"""
from copy import deepcopy
import uuid

from .domain.codec import digest
from .errors import LedgerError

TARGETS = ("OWN", "REVIEW", "REFERENCE", "DELEGATE")
EVIDENCE_OPERATIONS = {
    "explain": "SelfExplanationSubmitted",
    "counterexample": "CounterexampleIdentified",
    "apply": "AppliedInProject",
    "transfer": "TransferredToNewProblem",
}
EVENT_ACTORS = {
    "LearningCandidateRaised": "growth",
    "LearningCandidatesCollected": "local_cli",
    "LearningTargetSelected": "local_cli",
    "LearningDeferred": "local_cli",
    "LearningResumed": "local_cli",
    **{kind: "local_cli" for kind in EVIDENCE_OPERATIONS.values()},
}
from .learning_exercises import EVENT_ACTORS as EXERCISE_ACTORS
EVENT_ACTORS.update(EXERCISE_ACTORS)
from .learning_external import EVENT_ACTORS as EXTERNAL_LEARNING_ACTORS
EVENT_ACTORS.update(EXTERNAL_LEARNING_ACTORS)
CANDIDATE_FIELDS = (
    "id", "concept", "concept_id", "why_now", "project_anchor", "source_refs",
    "suggested_target", "minimum_model", "counterexample", "check", "system_capture", "origin",
)
SUBMISSION_STAGES = {
    "SelfExplanationSubmitted": "SELF_EXPLAINED",
    "CounterexampleIdentified": "COUNTEREXAMPLE_IDENTIFIED",
    "AppliedInProject": "APPLIED",
    "TransferredToNewProblem": "TRANSFERRED",
}


def _text(value, maximum=4000):
    from .domain.events import require
    require(type(value) is str and 1 <= len(value.strip()) and len(value) <= maximum)


def _refs(value):
    from .domain.events import require, uuid_value
    require(type(value) is list and 1 <= len(value) <= 32)
    require(all(type(ref) is str for ref in value) and len(value) == len(set(value)))
    for ref in value:
        parts = ref.split(":")
        require(len(parts) == 2)
        for part in parts:
            uuid_value(part)


def validate_payload(kind, payload):
    """Validate closed learning payloads, independently of the external proposal schema."""
    from .adapters.proposal_validation import valid_id
    from .domain.events import fields, hash_value, require
    require(kind in EVENT_ACTORS)
    if kind in EXTERNAL_LEARNING_ACTORS:
        from .learning_external import validate_payload as validate_external_payload
        validate_external_payload(kind, payload)
    elif kind in EXERCISE_ACTORS:
        from .learning_exercises import validate_payload as validate_exercise_payload
        validate_exercise_payload(kind, payload)
    elif kind == "LearningCandidateRaised":
        fields(payload, CANDIDATE_FIELDS)
        require(valid_id(payload["id"]) and valid_id(payload["concept_id"]))
        _text(payload["concept"], 1000)
        require(type(payload["why_now"]) is list and 1 <= len(payload["why_now"]) <= 32)
        for reason in payload["why_now"]:
            _text(reason)
        _refs(payload["source_refs"])
        require(payload["project_anchor"] in payload["source_refs"])
        require(payload["suggested_target"] in TARGETS)
        for field in ("minimum_model", "counterexample", "check"):
            _text(payload[field], 8000)
        require(type(payload["system_capture"]) is list and len(payload["system_capture"]) <= 4)
        require(all(item in ("REFERENCE", "PRECEDENT", "RULE", "TEST") for item in payload["system_capture"]))
        require(len(set(payload["system_capture"])) == len(payload["system_capture"]))
        require(payload["origin"] in ("TEMPLATE", "LOCAL", "EXTERNAL_RESPONSE"))
    elif kind == "LearningCandidatesCollected":
        fields(payload, ("candidate_ids",))
        ids = payload["candidate_ids"]
        require(type(ids) is list and len(ids) <= 3 and all(valid_id(item) for item in ids))
        require(len(ids) == len(set(ids)))
    elif kind == "LearningTargetSelected":
        fields(payload, ("candidate_id", "candidate_hash", "target", "reason"))
        require(valid_id(payload["candidate_id"]) and payload["target"] in TARGETS)
        hash_value(payload["candidate_hash"])
        _text(payload["reason"])
    elif kind in ("LearningDeferred", "LearningResumed"):
        fields(payload, ("candidate_id", "candidate_hash", "reason"))
        require(valid_id(payload["candidate_id"]))
        hash_value(payload["candidate_hash"])
        _text(payload["reason"])
    else:
        fields(payload, ("candidate_id", "candidate_hash", "statement", "source_refs", "evidence_basis"))
        require(valid_id(payload["candidate_id"]))
        hash_value(payload["candidate_hash"])
        _text(payload["statement"], 16000)
        _refs(payload["source_refs"])
        # This local entry point records submissions, never an independent examination.
        require(payload["evidence_basis"] == "SELF_REPORT")


def _known_refs(state, refs):
    from .domain.events import require
    sources = state.get("learning_source_events", {})
    require(all(ref in sources for ref in refs), "LEARNING_SOURCE")


def apply_event(state, event):
    """Apply to the reducer's private state and register every prior source in this run.

    The main reducer calls this for every event, after envelope/chain checks.
    Source metadata is small; neither source payloads nor file contents are copied.
    """
    from .domain.events import citation, require
    candidates = state.setdefault("learning_candidates", {})
    sources = state.setdefault("learning_source_events", {})
    kind, payload, ref = event["type"], event["payload"], citation(event)
    require(event["project_id"] == state["project_id"] and event["stream_id"] == state["run_id"], "STORE_INTEGRITY")
    require(ref not in sources, "STORE_INTEGRITY")
    if kind in EVENT_ACTORS:
        validate_payload(kind, payload)
        if kind in EXTERNAL_LEARNING_ACTORS:
            from .learning_external import apply_event as apply_external
            apply_external(state, event)
            item = None
        elif kind in EXERCISE_ACTORS:
            from .learning_exercises import apply_event as apply_exercise
            apply_exercise(state, event)
            # The exercise reducer writes its own history after checking the rubric.
            item = None
        elif kind == "LearningCandidateRaised":
            require(payload["id"] not in candidates, "LEARNING_CONFLICT")
            _known_refs(state, payload["source_refs"])
            if payload["origin"] == "TEMPLATE":
                from .growth import template_candidates
                templates = {item["id"]: candidate_payload(item) for item in template_candidates(state, include_off=True)}
                require(templates.get(payload["id"]) == payload, "LEARNING_SOURCE")
            elif payload["origin"] == "EXTERNAL_RESPONSE":
                from .responses import learning_payloads
                response = state.get("latest_response")
                require(response is not None and response["command_id"] == event["command_id"], "LEARNING_SOURCE")
                candidates_from_response = {item["id"]: item for item in learning_payloads(state)}
                require(candidates_from_response.get(payload["id"]) == payload, "LEARNING_SOURCE")
            item = {**deepcopy(payload), "candidate_hash": digest(payload), "source_ref": ref,
                    "owner_run": state["run_id"], "recorded": True,
                    "status": "OPEN", "cycle": 1, "ownership_target": payload["suggested_target"],
                    "target_is_suggestion": True, "target_ref": None, "evidence": [], "history": []}
            candidates[payload["id"]] = item
        elif kind == "LearningCandidatesCollected":
            require(all(candidate_id in candidates for candidate_id in payload["candidate_ids"]), "LEARNING_NOT_FOUND")
            item = None
        else:
            item = candidates.get(payload["candidate_id"])
            require(item is not None, "LEARNING_NOT_FOUND")
            require(item["candidate_hash"] == payload["candidate_hash"], "LEARNING_CONFLICT")
            if kind == "LearningTargetSelected":
                item.update(ownership_target=payload["target"], target_is_suggestion=False, target_ref=ref)
            elif kind == "LearningDeferred":
                require(item["status"] == "OPEN", "LEARNING_STAGE")
                item.update(status="DEFERRED")
            elif kind == "LearningResumed":
                require(item["status"] == "DEFERRED", "LEARNING_STAGE")
                item.update(status="OPEN", cycle=item["cycle"] + 1)
            else:
                require(item["status"] == "OPEN", "LEARNING_STAGE")
                _known_refs(state, payload["source_refs"])
                item["evidence"].append({"kind": kind, "statement": payload["statement"],
                                         "source_refs": deepcopy(payload["source_refs"]),
                                         "evidence_basis": payload["evidence_basis"], "externally_verified": False,
                                         "source_ref": ref, "recorded_at": event["recorded_at"], "cycle": item["cycle"]})
        if item is not None:
            item["history"].append({"type": kind, "source_ref": ref, "recorded_at": event["recorded_at"],
                                    "revision": event["revision"], "cycle": item["cycle"], "payload": deepcopy(payload)})
    sources[ref] = {"type": kind, "revision": event["revision"], "event_hash": event["event_hash"]}


def candidate_payload(suggestion):
    """Freeze the legacy deterministic candidate without inventing a selected target."""
    return {key: deepcopy(suggestion[key]) for key in CANDIDATE_FIELDS
            if key not in ("suggested_target", "origin")} | {
                "suggested_target": suggestion["ownership_target"], "origin": "TEMPLATE"}


def _project_candidate(item):
    result = deepcopy(item)
    stages = [SUBMISSION_STAGES[evidence["kind"]] for evidence in result["evidence"]]
    order = ["EXPOSED", *SUBMISSION_STAGES.values()]
    result.update(submission_state=max(["EXPOSED", *stages], key=order.index),
                  submission_stages=list(dict.fromkeys(stages)),
                  mastery_evidence="SELF_REPORTED" if stages else "NONE",
                  mastery_assessment="NOT_ASSESSED", assessment=None, externally_verified=False)
    if "exercises" in item:
        from .learning_exercises import project_exercises
        result["exercises"] = project_exercises(item)
        result["exercise_assessment_scope"] = "FIXED_QUESTIONS_ONLY"
    return result


def project_learning(state, *, include_deferred=True, include_suggestions=True):
    """Pure, complete curriculum view. The short Human Delta remains limited to 1–3."""
    if state is None:
        return []
    recorded = state.get("learning_candidates", {})
    result = [_project_candidate(item) for item in recorded.values()
              if include_deferred or item["status"] != "DEFERRED"]
    if include_suggestions:
        from .growth import template_candidates
        for item in template_candidates(state):
            if item["id"] not in recorded:
                result.append({**item, "recorded": False, "status": "SUGGESTED", "cycle": 0,
                               "evidence": [], "history": [], "submission_state": "EXPOSED",
                               "submission_stages": [], "mastery_assessment": "NOT_ASSESSED",
                               "externally_verified": False})
    return result


def learning_references(state, *, explicit_lookup=False):
    """Source-linked dictionary excerpts, excluding private submissions and feedback.

    The per-task 1–3 limit controls unsolicited suggestions. An explicit search
    may recover every recorded candidate, including a deferred item, without
    resuming it or changing its ownership target. It does not create suggestions
    for a task whose learning suggestions are off.
    """
    if state is None:
        return []
    off = state["learning_preferences"]["mode"] == "off"
    if off and not explicit_lookup:
        return []
    items = project_learning(state, include_deferred=explicit_lookup, include_suggestions=not off)
    if not explicit_lookup:
        items = items[:state["learning_preferences"]["max_items"]]
    fields = ("id", "concept", "concept_id", "why_now", "project_anchor", "ownership_target", "target_is_suggestion",
              "minimum_model", "counterexample", "check", "status", "source_refs", "system_capture", "recorded")
    return [{**{key: deepcopy(item[key]) for key in fields if key in item},
             "kind": "LEARNING_CANDIDATE", "owner_run": state["run_id"],
             "mastery_assessment": "NOT_ASSESSED", "authority": "REFERENCE_ONLY"} for item in items]


def is_learning_command(events, command_id):
    """Only learning records plus their closing evaluation may preserve a prior lease."""
    selected = [event for event in events if event["command_id"] == command_id]
    return bool(selected and selected[-1]["type"] == "EvaluationRecorded"
                and len(selected) > 1
                and all(event["type"] in EVENT_ACTORS for event in selected[:-1]))


def list_learning(root, configuration, run_id, archive_id=None):
    from .application import get_projection
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        view = get_projection(store, run_id, archive_id)
    state = view["state"]
    from .growth import deltas
    return {"schema_version": 1, "ok": True, "command": "learn", "run_id": run_id,
            "revision": state["revision"], "trust": state["trust"],
            "preferences": deepcopy(state["learning_preferences"]),
            "candidates": project_learning(state), **deltas(state)}


def _receipt_view(receipt, key):
    from .application import _receipt_view as base_view
    result = base_view(receipt, key)
    events = [event for event in receipt["events"] if event["command_id"] == receipt["command_id"]]
    ids = []
    for event in events:
        payload = event["payload"]
        if event["type"] == "LearningCandidateRaised":
            ids.append(payload["id"])
        elif event["type"] == "LearningCandidatesCollected":
            ids.extend(payload["candidate_ids"])
        elif event["type"] in EVENT_ACTORS:
            ids.append(payload["candidate_id"])
    ids = list(dict.fromkeys(ids))
    result.update(command="learning", candidate_ids=ids, candidates=project_learning(result["state"]))
    if len(ids) == 1:
        result["candidate_id"] = ids[0]
    return result


def control_learning(root, configuration, run_id, operation, *, candidate_id=None, key=None,
                     expected_revision=None, target=None, reason=None, concept=None, concept_id=None,
                     why_now=None, minimum_model=None, counterexample=None, check=None,
                     source_refs=(), statement=None, clock=None, suggested_target=None):
    """Append one voluntary operation with a normal hash-chain command receipt.

    collect saves existing suggestions; raise creates a locally supplied candidate.
    target/defer/resume and the four submission operations also materialize a named
    legacy suggestion on first use. No files, model, or execution backend are read.
    """
    from .adapters.proposal_validation import valid_id
    from .application import iso, now
    from .domain.events import make_event
    from .growth import template_candidates
    from .kernel.reducer import replay
    from .storage.sqlite import EventStore

    operations = {"collect", "raise", "target", "defer", "resume", *EVIDENCE_OPERATIONS}
    if operation not in operations or not valid_id(run_id):
        raise LedgerError("ARGUMENTS")
    key = str(uuid.uuid4()) if key is None else key
    if not valid_id(key) or (candidate_id is not None and not valid_id(candidate_id)):
        raise LedgerError("ARGUMENTS")
    if expected_revision is not None and (type(expected_revision) is not int or expected_revision < 0):
        raise LedgerError("ARGUMENTS")
    if type(source_refs) not in (list, tuple):
        raise LedgerError("ARGUMENTS")
    source_refs = list(source_refs)
    if type(why_now) is str:
        why_now = [why_now]
    # Reject irrelevant input instead of silently discarding a caller's intent.
    candidate_fields = (concept, concept_id, why_now, minimum_model, counterexample, check)
    if operation != "raise" and any(value is not None for value in candidate_fields):
        raise LedgerError("ARGUMENTS")
    if target is not None and operation != "target":
        raise LedgerError("ARGUMENTS")
    if reason is not None and operation not in ("target", "defer", "resume"):
        raise LedgerError("ARGUMENTS")
    if statement is not None and operation not in EVIDENCE_OPERATIONS:
        raise LedgerError("ARGUMENTS")
    if source_refs and operation not in {"raise", *EVIDENCE_OPERATIONS}:
        raise LedgerError("ARGUMENTS")
    if suggested_target is not None and (operation != "raise" or suggested_target not in TARGETS):
        raise LedgerError("ARGUMENTS")
    intent = {"operation": "learning." + operation, "run_id": run_id, "candidate_id": candidate_id,
              "expected_revision": expected_revision, "target": target, "reason": reason,
              "concept": concept, "concept_id": concept_id, "why_now": why_now,
              "minimum_model": minimum_model, "counterexample": counterexample, "check": check,
              "source_refs": source_refs, "statement": statement}
    if suggested_target is not None:
        intent["suggested_target"] = suggested_target
    input_hash = digest(intent)
    clock = clock or now
    project_id = configuration["project"]["id"]
    with EventStore(root, project_id, create=True) as store:
        receipt = store.receipt(key, input_hash)
        if receipt:
            return _receipt_view(receipt, key)
        project_revision = store.project_revision()
        previous = store.events(run_id)
        state = replay(previous)
        if state is None:
            raise LedgerError("RUN_NOT_FOUND")
        revision = state["revision"]
        if expected_revision is not None and expected_revision != revision:
            raise LedgerError("REVISION_CONFLICT", {"expected": expected_revision, "actual": revision})
        suggestions = {item["id"]: item for item in template_candidates(state, include_off=True)}
        candidates = state.get("learning_candidates", {})
        batch, command_id = [], str(uuid.uuid4())

        def add(kind, payload):
            nonlocal state, candidates
            event = make_event(project_id, run_id, revision + len(batch) + 1, command_id,
                               iso(clock()), kind, payload, str(uuid.uuid4()), batch[-1] if batch else previous[-1])
            batch.append(event)
            # Each subsequent action sees sources raised earlier in this same command.
            from .kernel.reducer import reduce_event
            state = reduce_event(state, event)
            candidates = state["learning_candidates"]

        def materialize(identity):
            if identity not in candidates:
                suggestion = suggestions.get(identity)
                if suggestion is None:
                    raise LedgerError("LEARNING_NOT_FOUND")
                add("LearningCandidateRaised", candidate_payload(suggestion))
            return candidates[identity]

        if operation == "collect":
            if candidate_id is not None:
                selected = [candidate_id]
            elif state["learning_preferences"]["mode"] == "off":
                selected = []
            else:
                selected = list(suggestions)[:state["learning_preferences"]["max_items"]]
            for identity in selected:
                materialize(identity)
            add("LearningCandidatesCollected", {"candidate_ids": selected})
        elif operation == "raise":
            identity = candidate_id or digest({"anchor": source_refs[0] if source_refs else None, "concept": concept_id})
            payload = {"id": identity, "concept": concept, "concept_id": concept_id, "why_now": why_now,
                       "project_anchor": source_refs[0] if source_refs else None, "source_refs": source_refs,
                       "suggested_target": suggested_target or "REVIEW", "minimum_model": minimum_model,
                       "counterexample": counterexample, "check": check, "system_capture": ["REFERENCE"], "origin": "LOCAL"}
            validate_payload("LearningCandidateRaised", payload)
            _known_refs(state, source_refs)
            if identity in candidates:
                if candidates[identity]["candidate_hash"] != digest(payload):
                    raise LedgerError("LEARNING_CONFLICT")
                add("LearningCandidatesCollected", {"candidate_ids": [identity]})
            else:
                add("LearningCandidateRaised", payload)
        else:
            if candidate_id is None:
                raise LedgerError("ARGUMENTS")
            item = materialize(candidate_id)
            payload = {"candidate_id": candidate_id, "candidate_hash": item["candidate_hash"]}
            if operation == "target":
                add("LearningTargetSelected", {**payload, "target": target, "reason": reason})
            elif operation in ("defer", "resume"):
                add("LearningDeferred" if operation == "defer" else "LearningResumed", {**payload, "reason": reason})
            else:
                add(EVIDENCE_OPERATIONS[operation], {**payload, "statement": statement,
                    "source_refs": source_refs or [item["source_ref"]], "evidence_basis": "SELF_REPORT"})
        add("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"})
        receipt = store.append(key, input_hash, run_id, revision, batch, project_revision=project_revision)
        return _receipt_view(receipt, key)
