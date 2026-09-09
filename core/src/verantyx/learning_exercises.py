"""Frozen, bounded learning exercises and opt-in review schedules.

The evaluator compares structured answers with a rubric registered before the
attempt. It assesses those answers only; it cannot certify who answered, infer
general understanding, or create a project verification or execution grant.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import uuid

from .domain.codec import canonical, digest
from .errors import LedgerError

EVENT_ACTORS = {
    "LearningExerciseRegistered": "local_cli",
    "LearningExerciseAttempted": "local_cli",
    "LearningExerciseAssessed": "learning_evaluator",
    "LearningReviewScheduled": "local_cli",
    "LearningReviewCancelled": "local_cli",
}
EVALUATOR = "verantyx.fixed-rubric.v1"
LOCALES = ("en", "ja", "zh-Hans", "ko", "es")
COMPETENCIES = ("SELF_EXPLANATION", "COUNTEREXAMPLE", "APPLICATION", "TRANSFER")
ORIGIN_FIELDS = ("kind", "identity", "model", "provider")
MAX_EXERCISE_BYTES = 65536


def _require(condition, code="LEARNING_EXERCISE_INVALID"):
    if not condition:
        raise LedgerError(code)


def _fields(value, names):
    _require(type(value) is dict and set(value) == set(names))


def _text(value, maximum=8000):
    _require(type(value) is str and 0 < len(value.strip()) <= len(value) <= maximum)


def _identity(value):
    from .adapters.proposal_validation import valid_id
    _require(valid_id(value))


def validate_origin(value):
    _fields(value, ORIGIN_FIELDS)
    _require(value["kind"] in ("LOCAL_OPERATOR", "EXTERNAL_MODEL", "MIXED", "UNKNOWN"))
    _text(value["identity"], 1000)
    for key in ("model", "provider"):
        if value[key] is not None:
            _text(value[key], 1000)
    if value["kind"] == "EXTERNAL_MODEL":
        _require(value["model"] is not None and value["provider"] is not None)


def _choices(value):
    _require(type(value) is list and 2 <= len(value) <= 12)
    ids = []
    for item in value:
        _fields(item, ("id", "label"))
        _identity(item["id"])
        _text(item["label"], 2000)
        ids.append(item["id"])
    _require(len(ids) == len(set(ids)))
    return ids


def _validate_answer(question, answer):
    if question["mode"] == "single_choice":
        _require(type(answer) is str and answer in [item["id"] for item in question["choices"]])
    elif question["mode"] == "select_all":
        _require(type(answer) is list and len(answer) <= len(question["choices"]))
        _require(all(type(item) is str for item in answer) and len(answer) == len(set(answer)))
        _require(set(answer) <= {item["id"] for item in question["choices"]})
    else:
        _fields(answer, [item["id"] for item in question["parts"]])
        for part in question["parts"]:
            _require(type(answer[part["id"]]) is str and answer[part["id"]] in [item["id"] for item in part["choices"]])


def validate_exercise(value):
    """Closed JSON data only: there is no executable rubric or arbitrary plugin."""
    _fields(value, ("schema_version", "id", "concept_id", "locale", "lesson", "questions", "passing_score", "provenance"))
    _require(type(value["schema_version"]) is int and value["schema_version"] == 1)
    _identity(value["id"])
    _identity(value["concept_id"])
    _require(value["locale"] in LOCALES)
    lesson = value["lesson"]
    _fields(lesson, ("title", "principle", "worked_example", "counterexample", "limitations", "sources"))
    for key in ("title", "principle", "worked_example", "counterexample"):
        _text(lesson[key])
    _require(type(lesson["limitations"]) is list and 1 <= len(lesson["limitations"]) <= 8)
    for limitation in lesson["limitations"]:
        _text(limitation, 2000)
    _require(type(lesson["sources"]) is list and 1 <= len(lesson["sources"]) <= 8)
    for source in lesson["sources"]:
        _fields(source, ("title", "locator", "version", "sha256"))
        for key in ("title", "locator", "version"):
            _text(source[key], 2000)
        if source["sha256"] is not None:
            from .domain.events import hash_value
            hash_value(source["sha256"])
    _require(type(value["questions"]) is list and 1 <= len(value["questions"]) <= 12)
    ids = []
    for question in value["questions"]:
        _require(type(question) is dict and question.get("mode") in ("single_choice", "select_all", "structured"))
        common = ("id", "mode", "competency", "prompt", "rubric")
        _fields(question, (*common, "parts" if question["mode"] == "structured" else "choices"))
        _identity(question["id"])
        ids.append(question["id"])
        _require(question["competency"] in COMPETENCIES)
        _text(question["prompt"])
        if question["mode"] == "structured":
            _require(type(question["parts"]) is list and 1 <= len(question["parts"]) <= 8)
            part_ids = []
            for part in question["parts"]:
                _fields(part, ("id", "prompt", "choices"))
                _identity(part["id"])
                _text(part["prompt"], 2000)
                _choices(part["choices"])
                part_ids.append(part["id"])
            _require(len(part_ids) == len(set(part_ids)))
        else:
            _choices(question["choices"])
        _fields(question["rubric"], ("expected",))
        _validate_answer(question, question["rubric"]["expected"])
    _require(len(ids) == len(set(ids)))
    _require(type(value["passing_score"]) is int and 1 <= value["passing_score"] <= len(ids))
    provenance = value["provenance"]
    _fields(provenance, ("author", "oracle", "data", "review"))
    validate_origin(provenance["author"])
    for key in ("oracle", "data", "review"):
        _text(provenance[key], 4000)
    _require(len(canonical(value).encode("utf-8")) <= MAX_EXERCISE_BYTES, "DOCUMENT_LIMIT")
    return value


def grade(exercise, answers, answer_origin):
    """Version-1 deterministic scoring, also used to verify replayed assessments."""
    validate_exercise(exercise)
    validate_origin(answer_origin)
    _fields(answers, [question["id"] for question in exercise["questions"]])
    results = []
    for question in exercise["questions"]:
        answer = answers[question["id"]]
        _validate_answer(question, answer)
        expected = question["rubric"]["expected"]
        matches = set(answer) == set(expected) if question["mode"] == "select_all" else answer == expected
        results.append({"question_id": question["id"], "competency": question["competency"], "matched": matches})
    author = exercise["provenance"]["author"]
    overlap = [key.upper() for key in ("identity", "model", "provider")
               if author[key] is not None and author[key] == answer_origin[key]]
    score = sum(item["matched"] for item in results)
    return {"method": "FIXED_RUBRIC", "evaluator": EVALUATOR,
            "exercise_hash": digest(exercise), "answer_hash": digest(answers),
            "score": score, "maximum": len(results), "passing_score": exercise["passing_score"],
            "status": "PASSED" if score >= exercise["passing_score"] else "FAILED", "closure": "BOUNDED",
            "question_results": results, "mastery_claim": "NOT_ASSESSED", "person_authenticated": False,
            "independence": {"status": "NOT_ESTABLISHED", "declared_overlap": overlap,
                             "rubric_author": deepcopy(author), "answer_origin": deepcopy(answer_origin),
                             "implementation": EVALUATOR, "dependencies": "Python standard library; no model grader",
                             "oracle": exercise["provenance"]["oracle"], "data": exercise["provenance"]["data"],
                             "environment": "LOCAL_PROCESS; rubric and answers visible to the OS account"}}


def public_exercise(exercise):
    result = deepcopy(exercise)
    for question in result["questions"]:
        del question["rubric"]
    result.update(exercise_hash=digest(exercise), rubric_visibility="OMITTED_FROM_VIEW; locally readable ledger")
    return result


def validate_payload(kind, payload):
    from .domain.events import hash_value, timestamp
    base = ("candidate_id", "candidate_hash", "exercise_id", "exercise_hash")
    _require(kind in EVENT_ACTORS)
    if kind == "LearningExerciseRegistered":
        _fields(payload, ("candidate_id", "candidate_hash", "exercise"))
        validate_exercise(payload["exercise"])
    elif kind == "LearningExerciseAttempted":
        _fields(payload, (*base, "attempt_id", "answers", "answer_origin"))
        _identity(payload["attempt_id"])
        _require(type(payload["answers"]) is dict)
        validate_origin(payload["answer_origin"])
    elif kind == "LearningExerciseAssessed":
        _fields(payload, (*base, "attempt_id", "attempt_ref", "result"))
        _identity(payload["attempt_id"])
        from .learning import _refs
        _refs([payload["attempt_ref"]])
        _require(type(payload["result"]) is dict)
    elif kind == "LearningReviewScheduled":
        _fields(payload, (*base, "due_at", "intervals_days", "reason"))
        timestamp(payload["due_at"])
        intervals = payload["intervals_days"]
        _require(type(intervals) is list and 1 <= len(intervals) <= 12)
        _require(all(type(value) is int and 1 <= value <= 365 for value in intervals))
        _require(intervals == sorted(set(intervals)))
        _text(payload["reason"], 4000)
    else:
        _fields(payload, (*base, "schedule_ref", "reason"))
        from .learning import _refs
        _refs([payload["schedule_ref"]])
        _text(payload["reason"], 4000)
    _identity(payload["candidate_id"])
    hash_value(payload["candidate_hash"])
    if kind != "LearningExerciseRegistered":
        _identity(payload["exercise_id"])
        hash_value(payload["exercise_hash"])


def _advance(schedule, assessed_at, assessment_ref, passed):
    step = schedule["step"] if passed else 0
    days = schedule["intervals_days"][step]
    due = datetime.strptime(assessed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    try:
        due += timedelta(days=days)
    except OverflowError:
        raise LedgerError("LEARNING_REVIEW_TIME") from None
    return {**schedule, "due_at": due.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "step": min(step + 1, len(schedule["intervals_days"]) - 1) if passed else 0,
            "last_assessment_ref": assessment_ref, "last_assessed_at": assessed_at,
            "completed_reviews": schedule["completed_reviews"] + 1}


def apply_event(state, event):
    """Called from learning.apply_event before registering this event as a source."""
    from .domain.events import citation
    kind, payload, ref = event["type"], event["payload"], citation(event)
    validate_payload(kind, payload)
    item = state["learning_candidates"].get(payload["candidate_id"])
    _require(item is not None, "LEARNING_NOT_FOUND")
    _require(item["candidate_hash"] == payload["candidate_hash"], "LEARNING_CONFLICT")
    exercises = item.setdefault("exercises", {})
    if kind == "LearningExerciseRegistered":
        spec = payload["exercise"]
        _require(spec["concept_id"] == item["concept_id"], "LEARNING_EXERCISE_CONFLICT")
        current = exercises.get(spec["id"])
        if current is not None:
            _require(current["exercise_hash"] == digest(spec), "LEARNING_EXERCISE_CONFLICT")
        else:
            _require(len(exercises) < 32, "DOCUMENT_LIMIT")
            exercises[spec["id"]] = {"specification": deepcopy(spec), "exercise_hash": digest(spec),
                                      "registered_ref": ref, "registered_revision": event["revision"], "registered_at": event["recorded_at"],
                                      "attempts": {}, "assessments": [], "review": None}
    else:
        exercise = exercises.get(payload["exercise_id"])
        _require(exercise is not None, "LEARNING_EXERCISE_NOT_FOUND")
        _require(exercise["exercise_hash"] == payload["exercise_hash"], "LEARNING_EXERCISE_CONFLICT")
        if kind == "LearningExerciseAttempted":
            _require(item["status"] == "OPEN", "LEARNING_STAGE")
            _require(payload["attempt_id"] not in exercise["attempts"], "LEARNING_EXERCISE_CONFLICT")
            _require(exercise["registered_revision"] < event["revision"], "LEARNING_EXERCISE_CONFLICT")
            _require(exercise["registered_at"] <= event["recorded_at"], "LEARNING_REVIEW_TIME")
            if exercise["assessments"]:
                _require(exercise["assessments"][-1]["recorded_at"] <= event["recorded_at"], "LEARNING_REVIEW_TIME")
            grade(exercise["specification"], payload["answers"], payload["answer_origin"])
            exercise["attempts"][payload["attempt_id"]] = {**deepcopy(payload), "source_ref": ref,
                "recorded_at": event["recorded_at"], "revision": event["revision"], "cycle": item["cycle"],
                "assessment_ref": None}
        elif kind == "LearningExerciseAssessed":
            attempt = exercise["attempts"].get(payload["attempt_id"])
            _require(attempt is not None and attempt["source_ref"] == payload["attempt_ref"], "LEARNING_SOURCE")
            _require(attempt["assessment_ref"] is None, "LEARNING_EXERCISE_CONFLICT")
            _require(item["status"] == "OPEN" and attempt["cycle"] == item["cycle"], "LEARNING_STAGE")
            _require(attempt["revision"] < event["revision"] and attempt["recorded_at"] <= event["recorded_at"], "LEARNING_EXERCISE_CONFLICT")
            expected = grade(exercise["specification"], attempt["answers"], attempt["answer_origin"])
            _require(canonical(payload["result"]) == canonical(expected), "LEARNING_ASSESSMENT_INVALID")
            attempt["assessment_ref"] = ref
            exercise["assessments"].append({**deepcopy(payload), "source_ref": ref,
                                           "recorded_at": event["recorded_at"], "cycle": attempt["cycle"]})
            schedule = exercise["review"]
            if schedule is not None and schedule["status"] == "SCHEDULED":
                _require(schedule["recorded_at"] <= event["recorded_at"], "LEARNING_REVIEW_TIME")
                # Early practice is scored and retained, but does not complete a
                # review that has not become due or accelerate its interval.
                if schedule["due_at"] <= event["recorded_at"]:
                    exercise["review"] = _advance(schedule, event["recorded_at"], ref, expected["status"] == "PASSED")
        elif kind == "LearningReviewScheduled":
            _require(item["status"] == "OPEN", "LEARNING_STAGE")
            _require(event["recorded_at"] <= payload["due_at"], "LEARNING_REVIEW_TIME")
            exercise["review"] = {"status": "SCHEDULED", "due_at": payload["due_at"],
                                   "intervals_days": deepcopy(payload["intervals_days"]), "step": 0,
                                   "source_ref": ref, "reason": payload["reason"], "recorded_at": event["recorded_at"],
                                   "last_assessment_ref": None, "last_assessed_at": None, "completed_reviews": 0}
        else:
            schedule = exercise["review"]
            _require(schedule is not None and schedule["status"] == "SCHEDULED", "LEARNING_STAGE")
            _require(schedule["source_ref"] == payload["schedule_ref"], "LEARNING_SOURCE")
            schedule.update(status="CANCELLED", cancelled_ref=ref, cancellation_reason=payload["reason"])
    item["history"].append({"type": kind, "source_ref": ref, "recorded_at": event["recorded_at"],
                            "revision": event["revision"], "cycle": item["cycle"], "payload": deepcopy(payload)})


def project_exercises(item):
    result = []
    for exercise_id, value in item.get("exercises", {}).items():
        result.append({"exercise_id": exercise_id, "exercise_hash": value["exercise_hash"],
                       "registered_ref": value["registered_ref"], "material": public_exercise(value["specification"]),
                       "attempts": deepcopy(list(value["attempts"].values())),
                       "assessments": deepcopy(value["assessments"]), "review": deepcopy(value["review"])})
    return result


def due_reviews(state, as_of):
    """Pure query with explicit UTC, limited by the task's voluntary preferences."""
    from .domain.events import timestamp
    timestamp(as_of)
    preferences = state["learning_preferences"]
    if preferences["mode"] == "off":
        return {"as_of": as_of, "total_due": 0, "items": [], "suppressed": "LEARNING_OFF"}
    due = []
    for item in state.get("learning_candidates", {}).values():
        if item["status"] != "OPEN" or (not item["target_is_suggestion"] and item["ownership_target"] == "DELEGATE"):
            continue
        for exercise_id, exercise in item.get("exercises", {}).items():
            schedule = exercise["review"]
            if schedule is not None and schedule["status"] == "SCHEDULED" and schedule["due_at"] <= as_of:
                due.append({"candidate_id": item["id"], "concept": item["concept"], "exercise_id": exercise_id,
                            "exercise_hash": exercise["exercise_hash"], "due_at": schedule["due_at"],
                            "schedule_ref": schedule["source_ref"], "step": schedule["step"],
                            "ownership_target": item["ownership_target"]})
    due.sort(key=lambda item: (item["due_at"], item["candidate_id"], item["exercise_id"]))
    return {"as_of": as_of, "total_due": len(due), "items": due[:preferences["max_items"]], "suppressed": None}


def inspect_exercises(root, configuration, run_id, *, candidate_id=None, exercise_id=None, archive_id=None,
                      as_of=None, clock=None):
    from .application import get_projection, iso, now
    from .learning import project_learning
    from .storage.sqlite import EventStore
    with EventStore(root, configuration["project"]["id"]) as store:
        view = get_projection(store, run_id, archive_id)
    state = view["state"]
    result = {"schema_version": 1, "ok": True, "run_id": run_id, "trust": state["trust"], "revision": state["revision"]}
    if candidate_id is None:
        query_state = state
        if archive_id is None:
            # Current display preferences can further suppress a historical task.
            # They do not rewrite its events, projected state, or old archives.
            preferences = deepcopy(state["learning_preferences"])
            if configuration["learning"]["mode"] == "off":
                preferences["mode"] = "off"
            preferences["max_items"] = min(preferences["max_items"], configuration["learning"]["max_items"])
            query_state = {**state, "learning_preferences": preferences}
        result.update(due_reviews(query_state, iso((clock or now)()) if as_of is None else as_of))
        return result
    candidates = {item["id"]: item for item in project_learning(state)}
    item = candidates.get(candidate_id)
    _require(item is not None, "LEARNING_NOT_FOUND")
    material = None
    if exercise_id is not None:
        exercise = state.get("learning_candidates", {}).get(candidate_id, {}).get("exercises", {}).get(exercise_id)
        _require(exercise is not None, "LEARNING_EXERCISE_NOT_FOUND")
        material = public_exercise(exercise["specification"])
    elif not item.get("exercises"):
        from .learning_materials import builtin_exercise
        material = public_exercise(builtin_exercise(item["concept_id"], state["locale"]))
    # This is the question/material view. Full submissions and append-only
    # history remain available through learn/events/export, not as nested
    # answer keys or private prior responses in a material JSON response.
    public_candidate = {key: deepcopy(item[key]) for key in ("id", "concept", "concept_id", "status", "cycle",
                        "ownership_target", "target_is_suggestion", "mastery_assessment", "externally_verified")}
    public_candidate["exercises"] = [{key: deepcopy(exercise[key]) for key in
                                    ("exercise_id", "exercise_hash", "registered_ref", "material", "review")}
                                    for exercise in item.get("exercises", [])]
    result.update(candidate_id=candidate_id, candidate=public_candidate, material=material)
    return result


def control_exercises(root, configuration, run_id, operation, *, candidate_id, exercise_id=None,
                      document=None, answers=None, answer_origin=None, due_at=None, intervals_days=None,
                      reason=None, key=None, expected_revision=None, clock=None):
    """Record an explicit exercise or schedule command in the same append-only ledger."""
    from .adapters.proposal_validation import valid_id
    from .application import iso, now
    from .domain.events import citation, make_event
    from .growth import template_candidates
    from .kernel.reducer import reduce_event, replay
    from .learning import _receipt_view, candidate_payload
    from .storage.sqlite import EventStore
    operations = ("register", "answer", "schedule", "cancel")
    _require(operation in operations and valid_id(run_id) and valid_id(candidate_id), "ARGUMENTS")
    _require(exercise_id is None or valid_id(exercise_id), "ARGUMENTS")
    _require(expected_revision is None or (type(expected_revision) is int and expected_revision >= 0), "ARGUMENTS")
    key = str(uuid.uuid4()) if key is None else key
    _require(valid_id(key), "ARGUMENTS")
    _require(document is None or operation == "register", "ARGUMENTS")
    _require((answers is None and answer_origin is None) or operation == "answer", "ARGUMENTS")
    _require((due_at is None and intervals_days is None) or operation == "schedule", "ARGUMENTS")
    _require(reason is None or operation in ("schedule", "cancel"), "ARGUMENTS")
    if operation != "register":
        _require(exercise_id is not None, "ARGUMENTS")
    intent = {"operation": "learning.exercise." + operation, "run_id": run_id, "candidate_id": candidate_id,
              "exercise_id": exercise_id, "document": document, "answers": answers, "answer_origin": answer_origin,
              "due_at": due_at, "intervals_days": intervals_days, "reason": reason, "expected_revision": expected_revision}
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
        _require(state is not None, "RUN_NOT_FOUND")
        revision = state["revision"]
        _require(expected_revision is None or expected_revision == revision, "REVISION_CONFLICT")
        batch, command_id = [], str(uuid.uuid4())

        def add(kind, payload):
            nonlocal state
            event = make_event(project_id, run_id, revision + len(batch) + 1, command_id, iso(clock()), kind,
                               payload, str(uuid.uuid4()), batch[-1] if batch else previous[-1])
            state = reduce_event(state, event)
            batch.append(event)
            return event

        if candidate_id not in state.get("learning_candidates", {}):
            templates = {item["id"]: item for item in template_candidates(state, include_off=True)}
            _require(candidate_id in templates, "LEARNING_NOT_FOUND")
            add("LearningCandidateRaised", candidate_payload(templates[candidate_id]))
        item = state["learning_candidates"][candidate_id]
        base = {"candidate_id": candidate_id, "candidate_hash": item["candidate_hash"]}
        if operation == "register":
            if document is None:
                from .learning_materials import builtin_exercise
                document = builtin_exercise(item["concept_id"], state["locale"])
            validate_exercise(document)
            _require(exercise_id is None or exercise_id == document["id"], "LEARNING_EXERCISE_CONFLICT")
            add("LearningExerciseRegistered", {**base, "exercise": deepcopy(document)})
        else:
            exercise = item.get("exercises", {}).get(exercise_id)
            _require(exercise is not None, "LEARNING_EXERCISE_NOT_FOUND")
            base.update(exercise_id=exercise_id, exercise_hash=exercise["exercise_hash"])
            if operation == "answer":
                # Answers never carry a result flag: this function computes it.
                if answer_origin is None:
                    answer_origin = {"kind": "UNKNOWN", "identity": "Unattributed local submission", "model": None, "provider": None}
                assessment = grade(exercise["specification"], answers, answer_origin)
                attempt_id = str(uuid.uuid4())
                attempt = add("LearningExerciseAttempted", {**base, "attempt_id": attempt_id,
                              "answers": deepcopy(answers), "answer_origin": deepcopy(answer_origin)})
                add("LearningExerciseAssessed", {**base, "attempt_id": attempt_id,
                    "attempt_ref": citation(attempt), "result": assessment})
            elif operation == "schedule":
                add("LearningReviewScheduled", {**base, "due_at": due_at,
                    "intervals_days": [1, 3, 7, 14] if intervals_days is None else intervals_days, "reason": reason})
            else:
                schedule = exercise["review"]
                _require(schedule is not None, "LEARNING_STAGE")
                add("LearningReviewCancelled", {**base, "schedule_ref": schedule["source_ref"], "reason": reason})
        add("EvaluationRecorded", {"as_of": iso(clock()), "evaluator": "m1.v1"})
        receipt = store.append(key, input_hash, run_id, revision, batch, project_revision=project_revision)
        return _receipt_view(receipt, key)
