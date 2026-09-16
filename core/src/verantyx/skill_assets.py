"""AI procedure drafts and voluntary human progress are independent, versioned axes.

No generated procedure grants a capability, certifies a person, or becomes executable.
The project reflection is the source; the personal catalogue is an optional local index.
"""
from copy import deepcopy
import json

from . import personal_profile as profile
from .domain.codec import canonical, digest
from .errors import LedgerError

PLANS = ("UNSELECTED", "WANT", "NEXT_TIME", "REFERENCE", "DELEGATE", "NOT_NEEDED")
HUMAN = ("NO_RECORD", "SELF_REPORTED", "EXPLAINED", "APPLIED", "TRANSFERRED")
AI_USE = ("DRAFT", "REFERENCE", "REVIEW_REQUIRED", "RETIRED")
ON_BOARD = ("WANT", "NEXT_TIME")
MARKS = {"NO_RECORD": "[ ]", "SELF_REPORTED": "[S]", "EXPLAINED": "[E]",
         "APPLIED": "[A]", "TRANSFERRED": "[T]"}


def candidate_schema():
    from .agent_schema import obj, array, TEXT, SOURCE
    nonempty = {"type": "string", "minLength": 1, "maxLength": 2000}
    return obj({
        "title": {"type": "string", "minLength": 1, "maxLength": 200},
        "purpose": nonempty,
        "technology_tags": array({"type": "string", "minLength": 1, "maxLength": 100}, 8),
        "inputs": array(nonempty, 8), "outputs": array(nonempty, 8),
        "steps": {**array(nonempty, 12), "minItems": 1},
        "applicable_when": {**array(nonempty, 8), "minItems": 1},
        "stop_when": array(nonempty, 8),
        "verification_methods": array(nonempty, 8),
        "human_decisions": array(nonempty, 8),
        "source_event_ids": {"type": "array", "items": SOURCE, "minItems": 1,
                             "maxItems": 16, "uniqueItems": True},
        "extends_skill_id": {**TEXT, "maxLength": 100},
    })


def validate_candidates(request, candidates):
    refs = {row["source_ref"] for row in request["trace"]["events"]}
    prior = {row["id"] for row in request.get("skill_context", {}).get("items", [])}
    for item in candidates:
        if not set(item["source_event_ids"]) <= refs:
            raise LedgerError("REFLECTION_SOURCE_UNKNOWN")
        if item["extends_skill_id"] and item["extends_skill_id"] not in prior:
            raise LedgerError("REFLECTION_SKILL_SOURCE_UNKNOWN")


def from_states(states, project_id, project_name):
    result = []
    for state in states:
        for reflection in state.get("work_reflections", []):
            if reflection["status"] != "PROPOSED":
                continue
            for index, item in enumerate((reflection.get("proposal") or {}).get("skill_candidates", [])):
                definition = deepcopy(item)
                identity = "skill-" + digest({"project": project_id, "run": state["run_id"],
                    "reflection": reflection["id"], "index": index, "definition": definition})[:40]
                result.append({
                    "id": identity, "kind": "skill_asset",
                    "work_key": project_id + "/" + state["run_id"],
                    "project_id": project_id, "project_name": project_name, "run_id": state["run_id"],
                    "reflection_id": reflection["id"], "source_ref": reflection["source_ref"],
                    "trace_sha256": reflection["trace_sha256"], "model": deepcopy(reflection["model"]),
                    "definition": definition, "definition_sha256": digest(definition),
                    "created_at": reflection["recorded_at"],
                    "authority": "AI_PROPOSAL_NOT_EXECUTION_OR_MASTERY",
                })
    return sorted(result, key=lambda row: (row["created_at"], row["id"]), reverse=True)


def project_assets(root, configuration):
    if root is None or configuration is None:
        return []
    from .owner_experience import read_states
    return from_states(read_states(root, configuration), configuration["project"]["id"],
                       configuration["project"]["name"])


def _cache(db, assets):
    added = 0
    for row in assets:
        old = profile._get(db, row["id"])
        if old is None:
            profile._put(db, row)
            added += 1
        elif old.get("kind") != "skill_asset" or old.get("definition_sha256") != row["definition_sha256"]:
            raise LedgerError("SKILL_VERSION_CHANGED")
    return added


def capture_safe(configuration, state):
    """Automatic indexing follows the existing personal-notebook opt-in."""
    try:
        if not profile.preferences()["enabled"]:
            return {"status": "PROJECT_ONLY", "human_progress_changed": False}
        assets = from_states([state], configuration["project"]["id"], configuration["project"]["name"])
        if not assets:
            return {"status": "NO_CANDIDATES", "human_progress_changed": False}
        with profile.connection(True) as db:
            added = _cache(db, assets)
        return {"status": "INDEXED", "added": added, "human_progress_changed": False}
    except Exception as error:
        return {"status": "INDEX_DEFERRED", "reason": getattr(error, "code", type(error).__name__),
                "project_reflections_retained": True, "human_progress_changed": False}


def sync_project(root, configuration):
    assets = project_assets(root, configuration)
    with profile.connection(True) as db:
        added = _cache(db, assets)
    return {"added": added, "project_candidates": len(assets), "sharing_enabled": False,
            "human_progress_changed": False}


def project_context(states, project_id, project_name):
    """A bounded context, not a lifetime cap and not an executable skill registry."""
    items, omitted, used = [], 0, 0
    assets = from_states(states, project_id, project_name)
    try:
        with profile.connection() as db:
            excluded = {row["id"] for row in assets
                        if _progress(db, row)["ai_use"] in ("RETIRED", "REVIEW_REQUIRED")}
    except Exception:
        return {"items": [], "omitted": len(assets), "status": "PERSONAL_CHOICES_UNAVAILABLE",
                "use": "UNVERIFIED_REFERENCE_ONLY", "human_progress_inferred": False,
                "execution_permissions": []}
    for row in assets:
        if row["id"] in excluded:
            omitted += 1
            continue
        value = {"id": row["id"], "definition": row["definition"],
                 "source_ref": row["source_ref"], "authority": row["authority"]}
        size = len(canonical(value).encode())
        if len(items) >= 8 or used + size > 20000:
            omitted += 1
            continue
        items.append(value)
        used += size
    return {"items": items, "omitted": omitted, "use": "UNVERIFIED_REFERENCE_ONLY",
            "human_progress_inferred": False, "execution_permissions": []}


def _progress(db, asset):
    row = profile._get(db, "progress-" + asset["id"])
    if row is not None:
        profile.require(row.get("asset_id") == asset["id"]
                        and row.get("definition_sha256") == asset["definition_sha256"],
                        "SKILL_VERSION_CHANGED")
        return row
    return {"id": "progress-" + asset["id"], "kind": "skill_progress", "asset_id": asset["id"],
            "definition_sha256": asset["definition_sha256"], "title": asset["definition"]["title"],
            "technology_tags": asset["definition"]["technology_tags"],
            "project_name": asset["project_name"], "plan": "UNSELECTED", "human": "NO_RECORD",
            "ai_use": "DRAFT", "note": "", "share_with_ai": False,
            "authority": "OWNER_SELF_REPORT_NOT_CERTIFICATION"}


def _global_page(db, *, exclude_project="", search="", offset=0, limit=18):
    if db is None:
        return [], 0
    clause = "kind='skill_asset'"
    params = []
    if exclude_project:
        prefix = exclude_project + "/"
        clause += " AND substr(work_key,1,?) != ?"
        params += [len(prefix), prefix]
    if search:
        clause += " AND instr(lower(document),lower(?)) > 0"
        params += [search]
    count = db.execute("SELECT COUNT(*) FROM records WHERE " + clause, params).fetchone()[0]
    rows = db.execute("SELECT document FROM records WHERE " + clause
                      + " ORDER BY updated DESC,id LIMIT ? OFFSET ?", [*params, limit, offset]).fetchall()
    return [json.loads(row[0]) for row in rows], count


def catalogue(root=None, configuration=None, *, page=0, search="", size=18):
    profile.require(type(page) is int and page >= 0 and type(search) is str and len(search) <= 200
                    and type(size) is int and 1 <= size <= 60, "SKILL_PAGE")
    current = project_assets(root, configuration)
    if search:
        current = [row for row in current if search.casefold() in canonical(row).casefold()]
    offset = page * size
    selected = current[offset:offset + size]
    with profile.connection() as db:
        others, total = _global_page(db, exclude_project=configuration["project"]["id"] if configuration else "",
            search=search, offset=max(0, offset - len(current)), limit=size - len(selected))
        selected += others
        rows = [{"asset": row, "progress": _progress(db, row)} for row in selected]
    return {"format": "verantyx.skill-catalogue.v1", "items": rows, "total": len(current) + total,
            "page": page, "page_size": size, "has_next": offset + size < len(current) + total,
            "automatic_execution": False, "personal_ability_inferred": False}


def resolve(identity, root=None, configuration=None):
    with profile.connection() as db:
        row = profile._get(db, identity)
    if row and row.get("kind") == "skill_asset":
        return row
    row = next((item for item in project_assets(root, configuration) if item["id"] == identity), None)
    profile.require(row is not None, "SKILL_REQUIRED")
    return row


def choose(asset, *, plan=None, human=None, ai_use=None, note="", share=None):
    profile.require(plan is None or plan in PLANS, "SKILL_PLAN")
    profile.require(human is None or human in HUMAN, "SKILL_HUMAN_STATE")
    profile.require(ai_use is None or ai_use in AI_USE, "SKILL_AI_USE")
    profile.require(type(note) is str and len(note) <= 4000
                    and (share is None or type(share) is bool), "SKILL_NOTE")
    profile.require(human not in ("EXPLAINED", "APPLIED", "TRANSFERRED") or note.strip(),
                    "SKILL_OWN_EXAMPLE_REQUIRED")
    profile.require(any(v is not None for v in (plan, human, ai_use, share)) or bool(note.strip()),
                    "SKILL_CHOICE_REQUIRED")
    with profile.connection(True) as db:
        _cache(db, [asset])
        row = _progress(db, asset)
        for name, value in (("plan", plan), ("human", human), ("ai_use", ai_use), ("share_with_ai", share)):
            if value is not None:
                row[name] = value
        if note.strip():
            row["note"] = note.strip()
        row["work_key"] = "skill-board" if row["plan"] in ON_BOARD else "skill-catalogue"
        row["created_at"] = row.get("created_at", profile.now())
        row["last_choice_by"] = "OWNER"
        row["execution_permissions"] = []
        return profile._put(db, row, history=True)


def board(*, page=0, size=9):
    profile.require(type(page) is int and page >= 0 and type(size) is int and 1 <= size <= 60,
                    "SKILL_PAGE")
    with profile.connection() as db:
        if db is None:
            return {"items": [], "total": 0, "page": page, "has_next": False}
        count = db.execute("SELECT COUNT(*) FROM records WHERE kind='skill_progress' "
                           "AND work_key='skill-board'").fetchone()[0]
        rows = db.execute("SELECT document FROM records WHERE kind='skill_progress' AND work_key='skill-board' "
                          "ORDER BY updated DESC,id LIMIT ? OFFSET ?", (size, page * size)).fetchall()
    return {"items": [json.loads(row[0]) for row in rows], "total": count, "page": page,
            "has_next": (page + 1) * size < count}


def history(identity, *, page=0):
    profile.require(type(page) is int and page >= 0, "SKILL_PAGE")
    with profile.connection() as db:
        if db is None:
            return []
        rows = db.execute("SELECT document,changed FROM history WHERE record_id=? "
                          "ORDER BY seq DESC LIMIT 30 OFFSET ?",
                          ("progress-" + identity, page * 30)).fetchall()
    return [{"record": json.loads(row[0]), "replaced_at": row[1]} for row in rows]


def shared_records(db, *, maximum=12, budget=24000):
    """Called only after the personal/global sharing opt-in, then require item consent."""
    if db is None:
        return {"items": [], "omitted": 0}
    items, omitted, used = [], 0, 0
    for stored in db.execute("SELECT document FROM records WHERE kind='skill_progress' ORDER BY updated DESC,id"):
        progress = json.loads(stored[0])
        if not progress.get("share_with_ai"):
            continue
        asset = profile._get(db, progress["asset_id"])
        if not asset:
            continue
        definition = asset["definition"]
        if progress["ai_use"] in ("RETIRED", "REVIEW_REQUIRED"):
            definition = {key: definition[key] for key in ("title", "technology_tags")}
        entry = {"id": asset["id"], "definition": definition,
                 "definition_sha256": asset["definition_sha256"], "source_ref": asset["source_ref"],
                 "owner_plan": progress["plan"], "human_self_report": progress["human"],
                 "owner_example": progress["note"], "ai_use": progress["ai_use"],
                 "authority": "REFERENCE_AND_SELF_REPORT_ONLY", "execution_permissions": []}
        size = len(canonical(entry).encode())
        if len(items) >= maximum or used + size > budget:
            omitted += 1
            continue
        items.append(entry)
        used += size
    return {"items": items, "omitted": omitted}


def portfolio(identities):
    profile.require(type(identities) is list and 1 <= len(identities) <= 100
                    and len(set(identities)) == len(identities), "SKILL_SELECTION")
    result = []
    with profile.connection() as db:
        for identity in identities:
            asset = profile._get(db, identity)
            profile.require(asset and asset["kind"] == "skill_asset", "SKILL_REQUIRED")
            row = _progress(db, asset)
            profile.require(row["human"] != "NO_RECORD", "SKILL_SELF_REPORT_REQUIRED")
            result.append({"skill_id": identity, "title": row["title"], "technology_tags": row["technology_tags"],
                           "project_name": row["project_name"], "human_self_report": row["human"],
                           "owner_example": row["note"], "AI_assisted": True})
    return {"format": "verantyx.personal-skills-portfolio.v1", "selected_skills": result,
            "authority": "OWNER_SELECTED_SELF_REPORT_NOT_CERTIFICATION", "published": False}
