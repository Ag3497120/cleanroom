"""Versioned source context and attributed interpretations, never authority.

Original requests are retained byte for byte. Finite meaning contracts describe
what an interpreter thinks they mean; agreement is not proof of that meaning.
"""
from copy import deepcopy
import hashlib
import uuid

from .domain.codec import canonical, digest
from .errors import LedgerError

FORMAT = "verantyx.shared-context.v1"
EVENT_ACTORS = {"SharedContextRecorded": "context_recorder", "HandoffPlanned": "context_interpreter",
                "EditorAttemptRecorded": "editor_gateway"}
DISPOSITIONS = ("NOW", "DEFERRED", "FORBIDDEN", "UNRESOLVED")
STRENGTHS = ("MUST", "SHOULD", "OPEN")
RELATIONS = ("PRIORITY_OVER", "DEPENDS_ON", "EXCEPTION_TO")
MAX_CONTEXT = 192 * 1024


def require(condition, code="SHARED_CONTEXT_INVALID"):
    if not condition:
        raise LedgerError(code)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names))


def text(value, limit=4000):
    require(type(value) is str and 0 < len(value.strip()) <= len(value) <= limit)


def identifier(value):
    from .adapters.proposal_validation import valid_id
    require(valid_id(value))


def sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_packet(packet):
    fields(packet, ("format", "project_id", "scope", "parent", "sources", "sha256"))
    require(packet["format"] == FORMAT)
    from .domain.events import context, uuid_value, hash_value
    uuid_value(packet["project_id"])
    context(packet["scope"])
    hash_value(packet["sha256"])
    require(digest({k: v for k, v in packet.items() if k != "sha256"}) == packet["sha256"])
    if packet["parent"] is not None:
        fields(packet["parent"], ("run_id", "revision", "sha256"))
        identifier(packet["parent"]["run_id"])
        require(type(packet["parent"]["revision"]) is int and packet["parent"]["revision"] > 0)
        hash_value(packet["parent"]["sha256"])
    sources = packet["sources"]
    require(type(sources) is list and 1 <= len(sources) <= 64, "SHARED_CONTEXT_LIMIT")
    for source in sources:
        fields(source, ("id", "run_id", "source_ref", "kind", "text", "sha256"))
        for key in ("id", "run_id", "source_ref"):
            identifier(source[key])
        require(source["kind"] == "USER_REQUEST" and source["id"] == source["source_ref"])
        text(source["text"], 16000)
        require(source["sha256"] == sha(source["text"]))
    require(len({s["id"] for s in sources}) == len(sources))
    require(len(canonical(packet).encode()) <= MAX_CONTEXT, "SHARED_CONTEXT_LIMIT")
    return packet


def make_packet(state, parent=None, original_request=None):
    sources, lineage = [], None
    if parent is not None:
        prior = parent.get("shared_context")
        require(prior is not None, "SHARED_CONTEXT_MISSING")
        validate_packet(prior)
        require(parent["project_id"] == state["project_id"] and parent["context"] == state["context"], "SHARED_CONTEXT_SCOPE")
        require(parent["run_id"] != state["run_id"], "SHARED_CONTEXT_SCOPE")
        sources = deepcopy(prior["sources"])
        lineage = {"run_id": parent["run_id"], "revision": parent["revision"], "sha256": prior["sha256"]}
    raw = original_request if original_request is not None else state["request"]
    # The console may supply its bounded conversational rendering separately.
    # It cannot substitute a different original for a plain request.
    if raw != state["request"]:
        from .domain.codec import decode
        rendered = decode(state["request"])
        require(type(rendered) is dict and rendered.get("current_request") == raw)
    sources.append({"id": state["request_ref"], "source_ref": state["request_ref"], "run_id": state["run_id"],
                    "kind": "USER_REQUEST", "text": raw, "sha256": sha(raw)})
    packet = {"format": FORMAT, "project_id": state["project_id"], "scope": deepcopy(state["context"]),
              "parent": lineage, "sources": sources}
    packet["sha256"] = digest(packet)
    return validate_packet(packet)


def validate_plan(plan, packet):
    fields(plan, ("context_sha256", "interpretations", "relations", "cases"))
    require(plan["context_sha256"] == packet["sha256"], "SHARED_CONTEXT_STALE")
    sources = {s["id"]: s for s in packet["sources"]}
    require(type(plan["interpretations"]) is list and 1 <= len(plan["interpretations"]) <= 64)
    nodes = {}
    for node in plan["interpretations"]:
        fields(node, ("id", "source_id", "quote", "meaning", "disposition", "strength", "alternatives"))
        identifier(node["id"])
        require(node["id"] not in nodes and type(node["source_id"]) is str and node["source_id"] in sources)
        text(node["quote"], 16000)
        require(node["quote"] in sources[node["source_id"]]["text"], "SHARED_CONTEXT_SOURCE")
        text(node["meaning"], 16000)
        require(node["disposition"] in DISPOSITIONS and node["strength"] in STRENGTHS)
        require(type(node["alternatives"]) is list and len(node["alternatives"]) <= 8)
        for alternative in node["alternatives"]:
            text(alternative)
        nodes[node["id"]] = node
    # Every retained request has an explicit interpretation or an unresolved one.
    require({n["source_id"] for n in nodes.values()} == set(sources), "SHARED_CONTEXT_OMITTED")
    require(type(plan["relations"]) is list and len(plan["relations"]) <= 128)
    for relation in plan["relations"]:
        fields(relation, ("kind", "from", "to"))
        require(relation["kind"] in RELATIONS and type(relation["from"]) is str and type(relation["to"]) is str)
        require(relation["from"] in nodes and relation["to"] in nodes and relation["from"] != relation["to"])
    require(len({canonical(r) for r in plan["relations"]}) == len(plan["relations"]))
    require(type(plan["cases"]) is list and 1 <= len(plan["cases"]) <= 32)
    ids = set()
    for case in plan["cases"]:
        fields(case, ("id", "situation", "choices", "expected", "interpretation_ids"))
        identifier(case["id"])
        require(case["id"] not in ids)
        ids.add(case["id"])
        text(case["situation"])
        require(type(case["choices"]) is list and 2 <= len(case["choices"]) <= 8)
        for choice in case["choices"]:
            fields(choice, ("id", "text"))
            identifier(choice["id"])
            text(choice["text"])
        choices = {c["id"] for c in case["choices"]}
        require(len(choices) == len(case["choices"]) and type(case["expected"]) is str and case["expected"] in choices)
        require(type(case["interpretation_ids"]) is list and 1 <= len(case["interpretation_ids"]) <= 64)
        require(all(type(i) is str and i in nodes for i in case["interpretation_ids"]))
        require(len(set(case["interpretation_ids"])) == len(case["interpretation_ids"]))
    require(len(canonical(plan).encode()) <= 96000, "SHARED_CONTEXT_LIMIT")
    return plan


def unresolved_plan(packet):
    nodes = [{"id": "source-" + str(i), "source_id": s["id"], "quote": s["text"], "meaning": s["text"],
              "disposition": "UNRESOLVED", "strength": "OPEN", "alternatives": []}
             for i, s in enumerate(packet["sources"])]
    # A template is intentionally unresolved. It is not a successful fallback.
    return {"context_sha256": packet["sha256"], "interpretations": nodes, "relations": [], "cases": [
        {"id": "clarify", "situation": "The intended change is still unresolved.",
         "choices": [{"id": "clarify", "text": "Keep the ambiguity explicit."},
                     {"id": "guess", "text": "Treat an unconfirmed guess as the user's decision."}],
         "expected": "clarify", "interpretation_ids": [n["id"] for n in nodes]}]}


def append(root, configuration, run_id, kind, payload, *, key, expected_revision):
    from .application import get_projection, _receipt_view, now, iso
    from .domain.events import make_event
    from .kernel.reducer import reduce_event
    from .storage.sqlite import EventStore
    intent = digest({"kind": kind, "payload": payload, "run_id": run_id, "revision": expected_revision})
    with EventStore(root, configuration["project"]["id"], create=True) as store:
        receipt = store.receipt(key, intent)
        if receipt:
            return _receipt_view(receipt, key)
        state = get_projection(store, run_id)["state"]
        require(state["revision"] == expected_revision, "REVISION_CONFLICT")
        previous = store.events(run_id)[-1]
        command_id, when = str(uuid.uuid4()), iso(now())
        event = make_event(configuration["project"]["id"], run_id, expected_revision + 1, command_id,
                           when, kind, payload, str(uuid.uuid4()), previous)
        updated = reduce_event(state, event)
        evaluation = make_event(configuration["project"]["id"], run_id, expected_revision + 2, command_id,
                                when, "EvaluationRecorded", {"as_of": when, "evaluator": "m1.v1"}, str(uuid.uuid4()), event)
        reduce_event(updated, evaluation)
        return _receipt_view(store.append(key, intent, run_id, expected_revision, [event, evaluation]), key)


def record_context(root, configuration, run_id, *, key, expected_revision, continue_from=None, original_request=None):
    from .application import get_projection
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        state = get_projection(store, run_id)["state"]
        if state.get("shared_context"):
            # Return the original command receipt, rather than binding a retry
            # to the parent's possibly newer revision.
            return append(root, configuration, run_id, "SharedContextRecorded",
                          {"basis_revision": expected_revision, "packet": state["shared_context"]},
                          key=key, expected_revision=expected_revision)
        parent = get_projection(store, continue_from)["state"] if continue_from else None
        packet = make_packet(state, parent, original_request)
    return append(root, configuration, run_id, "SharedContextRecorded", {"basis_revision": expected_revision, "packet": packet},
                  key=key, expected_revision=expected_revision)


def validate_payload(kind, payload):
    if kind == "SharedContextRecorded":
        fields(payload, ("basis_revision", "packet"))
        validate_packet(payload["packet"])
    elif kind == "HandoffPlanned":
        names = {"basis_revision", "context_sha256", "plan", "provenance", "request_sha256"}
        fields(payload, names | ({"decision_context", "external_captures", "reconsideration"} & set(payload)))
        if "reconsideration" in payload:
            fields(payload["reconsideration"], ("plan_ref", "editor_ref", "mismatch_ids"))
    elif kind == "EditorAttemptRecorded":
        fields(payload, ("basis_revision", "context_sha256", "plan_sha256", "document", "validation", "provenance", "request_sha256", "selected_files"))
    else:
        require(False)
    require(type(payload["basis_revision"]) is int and payload["basis_revision"] > 0)
    if kind != "SharedContextRecorded":
        from .domain.events import hash_value
        for key in ("context_sha256", "request_sha256"):
            hash_value(payload[key])
        fields(payload["provenance"], ("role", "adapter_sha256", "provider", "model"))
        require(payload["provenance"]["role"] == ("VERA_INTERPRETER" if kind == "HandoffPlanned" else "CODE_EDITOR"))
        hash_value(payload["provenance"]["adapter_sha256"])
        for key in ("provider", "model"):
            text(payload["provenance"][key], 1000)


def current_editor_attempt(state):
    """Return the latest result only when it belongs to the current plan event.

    Equal plan documents are not the same planning attempt. The event reference
    is derived during replay, so existing event payloads remain unchanged.
    """
    plan, attempt = state.get("handoff_plan"), state.get("editor_attempt")
    history = state.get("editor_attempts", [])
    if not plan or not attempt or not history or not state.get("shared_context"):
        return None
    if (not plan.get("source_ref") or attempt.get("plan_ref") != plan["source_ref"]
            or attempt.get("source_ref") != history[-1].get("source_ref")
            or attempt.get("context_sha256") != state["shared_context"]["sha256"]
            or attempt.get("plan_sha256") != digest(plan["plan"])):
        return None
    return attempt


def require_source_constraints(original, proposal):
    """A model revision cannot silently discard a handoff's recorded constraints."""
    require(type(original) is dict and type(proposal) is dict, "EDITOR_CONSTRAINT_CHANGED")
    for group in ("decision_points", "unknowns", "claims"):
        current = {row["id"]: row for row in proposal.get(group, [])}
        require(all(row["id"] in current and digest(row) == digest(current[row["id"]])
                    for row in original.get(group, [])), "EDITOR_CONSTRAINT_CHANGED")


def apply_event(state, event):
    kind, p = event["type"], event["payload"]
    if kind not in EVENT_ACTORS:
        return
    from .domain.events import citation
    validate_payload(kind, p)
    require(state["revision"] == p["basis_revision"], "SHARED_CONTEXT_STALE")
    if kind == "SharedContextRecorded":
        packet = p["packet"]
        require(not state.get("shared_context"))
        require(packet["project_id"] == state["project_id"] and packet["scope"] == state["context"])
        last = packet["sources"][-1]
        require(last["source_ref"] == state["request_ref"] and last["run_id"] == state["run_id"])
        # Recheck the exact original binding without loading a parent or file.
        make_packet(state, original_request=last["text"])
        state["shared_context"] = deepcopy(packet)
        state["shared_context_ref"] = citation(event)
    else:
        packet = state.get("shared_context")
        require(packet is not None and p["context_sha256"] == packet["sha256"], "SHARED_CONTEXT_STALE")
        item = {**deepcopy(p), "source_ref": citation(event), "evidence_role": "MODEL_INTERPRETATION"}
        if kind == "HandoffPlanned":
            validate_plan(p["plan"], packet)
            if "external_captures" in p:
                require(p["external_captures"] == state.get("external_captures", []), "SHARED_CONTEXT_INVALID")
            if "decision_context" in p:
                from .decision_context import snapshot
                require(p["decision_context"] == snapshot(state), "SHARED_CONTEXT_INVALID")
            previous = state.get("handoff_plan")
            if "reconsideration" in p:
                attempt = current_editor_attempt(state)
                require(previous is not None and attempt is not None, "SHARED_CONTEXT_STALE")
                require(p["reconsideration"] == {
                    "plan_ref": previous["source_ref"], "editor_ref": attempt["source_ref"],
                    "mismatch_ids": attempt["validation"]["mismatch_ids"]}, "SHARED_CONTEXT_STALE")
                require(attempt["validation"]["status"] == "REPAIR_REQUIRED")
            if previous:
                require_source_constraints(previous["source_proposal"], state["proposal"])
            # Capture the actual proposal that this handoff is extending. These
            # fields are derived from prior events, never supplied by a model.
            item["source_proposal"] = deepcopy(state["proposal"])
            item["source_proposal_ref"] = state["proposal_ref"]
            state.setdefault("handoff_plans", []).append(item)
            state["handoff_plan"] = item
            # A new plan has no result; preserve all earlier attempts as history.
            state["editor_attempt"] = None
        else:
            from .coordination import validate_editor, comparison_inputs
            from .adapters.cross_context import validate_result
            plan = state.get("handoff_plan")
            require(plan is not None and digest(plan["plan"]) == p["plan_sha256"], "SHARED_CONTEXT_STALE")
            validate_editor(p["document"], packet, plan["plan"])
            require(type(p["selected_files"]) is list and len(p["selected_files"]) <= 16)
            selected = set()
            for source in p["selected_files"]:
                fields(source, ("path", "sha256", "source_ref"))
                require(type(source["path"]) is str and source["path"] in state["read_scope"] and source["path"] not in selected)
                selected.add(source["path"])
                require(type(source["source_ref"]) is str)
                observed = state["observations"].get(source["source_ref"])
                require(observed is not None and observed["path"] == source["path"] and observed["sha256"] == source["sha256"])
            from .coordination_schema import validate_editor_test_contract
            validate_editor_test_contract(p["document"], p["selected_files"])
            validate_result(p["validation"], comparison_inputs(packet, plan["plan"], p["document"]))
            require(p["provenance"]["adapter_sha256"] != plan["provenance"]["adapter_sha256"], "EDITOR_ROLE_COLLISION")
            item["plan_ref"] = plan["source_ref"]
            state.setdefault("editor_attempts", []).append(item)
            state["editor_attempt"] = item
