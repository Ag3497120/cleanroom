"""Voluntary model materials and scoped feedback on an explicitly selected answer.

External feedback is attributed data, not a kernel verifier, human examination,
or a permission. Reducer checks never call the model or read current files.
"""
from copy import deepcopy
import uuid

from .domain.codec import canonical, decode, digest
from .errors import LedgerError

EVENT_ACTORS = {"LearningMaterialProposed": "external_learning", "LearningExternalAssessmentRecorded": "external_learning"}
FORMAT = "verantyx.learning-request.v1"


def _require(condition, code="LEARNING_EXERCISE_INVALID"):
    if not condition:
        raise LedgerError(code)


def _text(value, maximum=8000):
    _require(type(value) is str and 0 < len(value.strip()) <= len(value) <= maximum)


def _request(state, candidate_id, operation, submission_ref=None, rubric=None):
    from .adapters.proposal_validation import valid_id
    _require(valid_id(candidate_id) and operation in ("material", "assess"), "ARGUMENTS")
    item = state.get("learning_candidates", {}).get(candidate_id)
    _require(item is not None, "LEARNING_NOT_FOUND")
    _require(item["status"] == "OPEN", "LEARNING_STAGE")
    submission = None
    source_refs = [item["source_ref"]]
    if operation == "assess":
        _text(rubric, 4000)
        matches = [e for e in item["evidence"] if e["source_ref"] == submission_ref and e["cycle"] == item["cycle"]]
        _require(len(matches) == 1, "LEARNING_SOURCE")
        evidence = matches[0]
        submission = {"source_ref": submission_ref, "sha256": digest(evidence), "statement": evidence["statement"],
                      "kind": evidence["kind"], "origin": "LOCAL_SELF_REPORT_IDENTITY_NOT_VERIFIED"}
        source_refs.append(submission_ref)
    else:
        _require(submission_ref is None and rubric is None, "ARGUMENTS")
    template = {"schema_version": 1, "kind": "MATERIAL_PROPOSAL" if operation == "material" else "ANSWER_ASSESSMENT",
                "candidate_id": candidate_id, "candidate_hash": item["candidate_hash"], "cycle": item["cycle"],
                "scope": "SELECTED_CANDIDATE_ONLY" if operation == "material" else "SELECTED_SUBMISSION_AND_RUBRIC_ONLY",
                "source_refs": source_refs, "limitations": ["Generated content requires human review; identity and mastery are not assessed."]}
    if operation == "material":
        template["content"] = {key: "Replace with a scoped teaching suggestion." for key in
                               ("title", "principle", "worked_example", "counterexample", "check")}
    else:
        template.update(content="Feedback on this submitted answer only.", assessment="UNKNOWN",
                        submission_ref=submission_ref, submission_sha256=submission["sha256"], rubric=rubric)
    return {"format": FORMAT, "task_id": state["run_id"], "context_revision": state["revision"],
            "response_locale": state["locale"], "operation": operation,
            "candidate": {key: deepcopy(item[key]) for key in ("id", "concept", "concept_id", "candidate_hash", "cycle", "why_now", "minimum_model")},
            "submission": submission, "rubric": rubric, "source_refs": source_refs,
            "response_template": template,
            "output_contract": "Return one JSON object with exactly the response_template fields and fixed identifiers, scope and sources. "
                               "Replace only content and limitations; for assessment select SUPPORTED, GAPS, or UNKNOWN. "
                               "Feedback applies only to the selected submission under the supplied rubric; never certify human mastery or identity. "
                               "Materials must remain suggestions with a counterexample and check. No execution or authority fields."}


def validate_response(value, request):
    _require(type(value) is dict and type(request) is dict and request.get("format") == FORMAT)
    template = request["response_template"]
    _require(set(value) == set(template))
    _require(type(value.get("schema_version")) is int and type(value.get("cycle")) is int)
    mutable = {"content", "limitations", "assessment"}
    # Canonical comparison distinguishes JSON booleans and integers.
    _require(all(canonical(value[key]) == canonical(template[key]) for key in template if key not in mutable))
    limits = value["limitations"]
    _require(type(limits) is list and 1 <= len(limits) <= 8)
    for item in limits:
        _text(item, 2000)
    if request["operation"] == "material":
        _require(type(value["content"]) is dict and set(value["content"]) == set(template["content"]))
        for content in value["content"].values():
            _text(content)
    else:
        _text(value["content"], 16000)
        _require(value["assessment"] in ("SUPPORTED", "GAPS", "UNKNOWN"))
    _require(len(canonical(value).encode()) <= 65536, "DOCUMENT_LIMIT")
    return value


def validate_payload(kind, payload):
    from .adapters.proposal_validation import valid_id
    from .domain.events import fields, hash_value, require
    require(kind in EVENT_ACTORS)
    fields(payload, ("candidate_id", "candidate_hash", "cycle", "requested_revision", "request_sha256", "response_sha256",
                     "adapter_identity", "provenance", "response", "mastery_assessment", "oracle_independence"))
    require(valid_id(payload["candidate_id"]) and type(payload["cycle"]) is int and payload["cycle"] >= 1)
    require(type(payload["requested_revision"]) is int and payload["requested_revision"] > 0)
    for key in ("candidate_hash", "request_sha256", "response_sha256", "adapter_identity"):
        hash_value(payload[key])
    fields(payload["provenance"], ("transport", "provider", "model", "endpoint_sha256"))
    require(payload["provenance"]["transport"] in ("MODEL_API", "LOCAL_COMMAND"))
    for key in ("provider", "model"):
        _text(payload["provenance"][key], 1000)
    if payload["provenance"]["endpoint_sha256"] is not None:
        hash_value(payload["provenance"]["endpoint_sha256"])
    require(payload["mastery_assessment"] == "NOT_ASSESSED" and payload["oracle_independence"] == "NOT_ESTABLISHED")
    require(type(payload["response"]) is dict and digest(payload["response"]) == payload["response_sha256"])


def apply_event(state, event):
    from .domain.events import citation, require
    payload, kind = event["payload"], event["type"]
    validate_payload(kind, payload)
    item = state["learning_candidates"].get(payload["candidate_id"])
    require(item is not None and item["candidate_hash"] == payload["candidate_hash"] and item["cycle"] == payload["cycle"], "LEARNING_CONFLICT")
    require(event["revision"] == payload["requested_revision"] + 1, "REVISION_CONFLICT")
    response = payload["response"]
    operation = "material" if kind == "LearningMaterialProposed" else "assess"
    # Reconstruct the exact request snapshot; no current external inputs are read.
    request = _request({**state, "revision": payload["requested_revision"]}, item["id"], operation,
                       response.get("submission_ref"), response.get("rubric"))
    validate_response(response, request)
    require(digest(request) == payload["request_sha256"], "LEARNING_SOURCE")
    key = "external_materials" if operation == "material" else "external_assessments"
    item.setdefault(key, []).append({"source_ref": citation(event), "recorded_at": event["recorded_at"], **deepcopy(payload)})
    item["history"].append({"type": kind, "source_ref": citation(event), "recorded_at": event["recorded_at"],
                            "revision": event["revision"], "cycle": item["cycle"], "payload": deepcopy(payload)})


def generate(root, configuration, run_id, *, candidate_id, operation, adapter_path, key, expected_revision,
             submission_ref=None, rubric=None, timeout=60, clock=None, fault=None):
    from .adapters.command_process import BoundedProcess, load_command
    from .adapters.invocation_journal import InvocationJournal
    from .adapters.proposal_validation import valid_id
    from .application import get_projection, iso, now
    from .domain.events import make_event
    from .jobs import _executor_fingerprint
    from .kernel.reducer import reduce_event
    from .learning import _receipt_view
    from .storage.sqlite import EventStore
    _require(valid_id(run_id) and valid_id(key) and type(expected_revision) is int and expected_revision > 0, "ARGUMENTS")
    _require(type(timeout) is int and 1 <= timeout <= 600, "ARGUMENTS")
    command = load_command(adapter_path)
    executor = _executor_fingerprint(command)
    model = command.get("model_api")
    provenance = {"transport": "MODEL_API" if model else "LOCAL_COMMAND",
                  "provider": model["provider"] if model else "explicit_local_command",
                  "model": model["model"] if model else "unspecified_external_evaluator",
                  "endpoint_sha256": digest(model["endpoint"]) if model else None}
    intent = {"run_id": run_id, "candidate_id": candidate_id, "operation": operation, "expected_revision": expected_revision,
              "submission_ref": submission_ref, "rubric": rubric, "executor": executor, "timeout": timeout,
              "project_id": configuration["project"]["id"]}
    intent_hash = digest(intent)
    clock = clock or now
    with InvocationJournal(root, "learning-model", key) as journal:
        started = journal.read("started")
        if started:
            _require(started.get("intent_hash") == intent_hash, "IDEMPOTENCY_CONFLICT")
        else:
            with EventStore(root, configuration["project"]["id"]) as store:
                project_revision = store.project_revision()
                state = get_projection(store, run_id)["state"]
                _require(state["revision"] == expected_revision, "REVISION_CONFLICT")
                value = _request(state, candidate_id, operation, submission_ref, rubric)
            started = {"intent_hash": intent_hash, "request_sha256": digest(value), "project_revision": project_revision}
            journal.write("started", started)
            if fault:
                fault("after_started")
            try:
                _require(_executor_fingerprint(load_command(adapter_path)) == executor, "JOB_ADAPTER_CHANGED")
                with EventStore(root, configuration["project"]["id"]) as store:
                    _require(store.project_revision() == project_revision, "REVISION_CONFLICT")
                with BoundedProcess(command, timeout=timeout, max_output=262144) as process:
                    response = validate_response(decode(process.document(value), 65536), value)
                journal.write("response", response)
                if fault:
                    fault("after_response")
            except LedgerError as error:
                # Do not retain arbitrary generator diagnostics or returned fields.
                journal.write("failed", {"code": error.code})
                raise LedgerError(error.code) from None
        failed = journal.read("failed")
        if failed:
            raise LedgerError(failed["code"])
        response = journal.read("response")
        if response is None:
            raise LedgerError("BRIDGE_OUTCOME_UNKNOWN")
        with EventStore(root, configuration["project"]["id"], create=True) as store:
            receipt_key = "learning-model-" + journal.prefix
            receipt = store.receipt(receipt_key, intent_hash)
            if receipt:
                return {**_receipt_view(receipt, receipt_key), "external_call_repeated": False}
            _require(store.project_revision() == started["project_revision"], "REVISION_CONFLICT")
            previous = store.events(run_id)
            state = get_projection(store, run_id)["state"]
            _require(state["revision"] == expected_revision, "REVISION_CONFLICT")
            value = _request(state, candidate_id, operation, submission_ref, rubric)
            _require(digest(value) == started["request_sha256"], "LEARNING_SOURCE")
            validate_response(response, value)
            event_kind = "LearningMaterialProposed" if operation == "material" else "LearningExternalAssessmentRecorded"
            payload = {"candidate_id": candidate_id, "candidate_hash": value["candidate"]["candidate_hash"],
                       "cycle": value["candidate"]["cycle"], "requested_revision": expected_revision,
                       "request_sha256": digest(value), "response_sha256": digest(response), "adapter_identity": executor,
                       "provenance": provenance, "response": response, "mastery_assessment": "NOT_ASSESSED",
                       "oracle_independence": "NOT_ESTABLISHED"}
            command_id = str(uuid.uuid4())
            event = make_event(configuration["project"]["id"], run_id, expected_revision + 1, command_id, iso(clock()),
                               event_kind, payload, str(uuid.uuid4()), previous[-1])
            reduce_event(state, event)
            evaluation = make_event(configuration["project"]["id"], run_id, expected_revision + 2, command_id, iso(clock()),
                                    "EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"}, str(uuid.uuid4()), event)
            receipt = store.append(receipt_key, intent_hash, run_id, expected_revision, [event, evaluation],
                                   project_revision=started["project_revision"])
            if fault:
                fault("after_record")
            return {**_receipt_view(receipt, receipt_key), "external_call_repeated": False,
                    "external_result": response, "provenance": provenance}
