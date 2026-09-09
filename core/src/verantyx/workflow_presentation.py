"""Bounded views of recorded asset checks; generated prose cannot replace them."""
from copy import deepcopy


def snapshot(state, *, as_of=None, version=2):
    items = (state or {}).get("asset_workflows", {})
    if not items:
        return None
    identity, item = next(reversed(items.items()))
    plan = item["plan"]
    results = deepcopy(item.get("results", []))
    refs = [item["source_ref"]]
    if item.get("finished_ref"):
        refs.append(item["finished_ref"])
    refs.extend(row["source_ref"] for row in results)
    value = {"id": identity, "status": item["status"], "source_refs": list(dict.fromkeys(refs)),
            "steps": [{"id": row["id"], "mode": row["mode"], "target_path": row["spec"]["target_path"],
                       "property": row["spec"]["property"], "expectation_origin": row["expectation_origin"]}
                      for row in plan["steps"]],
            "results": results, "unresolved": deepcopy(plan["document"]["unresolved"]),
            "rejected_plans": len(plan["rejected"]), "authority_granted": False,
            "prose_entailment": "NOT_ASSESSED", "independence": "NOT_ESTABLISHED"}
    if version == 1:
        # Early workflow answers had no currentness fields. Preserve their
        # recorded model input verbatim when replaying those response events.
        return value
    from .domain.codec import canonical, digest
    from .domain.events import timestamp
    from .decision_context import snapshot as decision_snapshot
    as_of = as_of or state["evaluated_at"]
    timestamp(as_of)
    context, reasons = plan["context"], []
    if "external_captures" in context and context["external_captures"] != state.get("external_captures", []):
        reasons.append("REFERENCE_CHANGED")
    if digest(state.get("proposal")) != context["proposal_hash"]:
        reasons.append("PROPOSAL_CHANGED")
    if canonical(decision_snapshot(state)["items"]) != canonical(context["decision_context"]["items"]):
        reasons.append("DECISION_CHANGED")
    for row in context["selected_files"]:
        ref = state.get("latest_observations", {}).get(row["path"])
        observation = state.get("observations", {}).get(ref)
        if not observation or observation["status"] != "OBSERVED" or observation["sha256"] != row["sha256"]:
            reasons.append("SELECTED_FILE_CHANGED")
        elif not observation["observed_at"] <= as_of < observation["expires_at"]:
            reasons.append("OBSERVATION_EXPIRED")
    for result in results:
        verification = state.get("verifications", {}).get(result["verification_id"])
        if not verification or as_of >= verification["plan"]["expires_at"]:
            reasons.append("RESULT_EXPIRED")
    if not results and as_of >= plan["expires_at"]:
        reasons.append("PLAN_EXPIRED")
    value.update(currentness="HISTORICAL" if reasons else "CURRENT", as_of=as_of,
                 currentness_basis="RECORDED_STATE_AT_EXPLICIT_TIME",
                 stale_reasons=list(dict.fromkeys(reasons)))
    return value


def lines(state, locale, *, as_of=None):
    from .i18n import text
    from .presentation import safe_text
    from .application import iso, now
    if not (state or {}).get("asset_workflows"):
        return []
    value = snapshot(state, as_of=as_of or iso(now()))
    if value is None:
        return []
    output = []
    if value["currentness"] == "HISTORICAL":
        output.append(text(locale, "workflow.historical"))
        output.extend(text(locale, "workflow.stale." + reason) for reason in value["stale_reasons"])
    output.append(text(locale, "workflow.status." + value["status"]))
    by_step = {row["step_id"]: row for row in value["results"]}
    for step in value["steps"]:
        outcome = by_step.get(step["id"])
        output.append(text(locale, "workflow.target", target=safe_text(step["target_path"]),
                           property=safe_text(step["property"])))
        if outcome:
            output.append(text(locale, "workflow.result." + (outcome["closure"] or "UNKNOWN")))
    for reason in value["unresolved"]:
        output.append(text(locale, "workflow.reason." + reason) if reason in
                      ("NO_CURRENT_CLAIMS", "NO_SELECTED_TARGETS", "PLANNING_REJECTED") else safe_text(reason))
    output.append(text(locale, "workflow.boundary"))
    return output
