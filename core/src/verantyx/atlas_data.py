"""Read-only projections of owner-written experience, never inferred ability."""
from collections import Counter
from datetime import datetime, timezone
import json

from . import personal_profile as profile
from .skill_assets import HUMAN, ON_BOARD

EXPERIENCE = tuple(value for value in HUMAN if value != "NO_RECORD")
FEEDBACK = {"SELF_REPORTED_UNDERSTOOD": "SELF_REPORTED", "SELF_REPORTED_APPLIED": "APPLIED",
            "SELF_REPORTED_TRANSFERRED": "TRANSFERRED"}


def _date(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()
    except (ValueError, TypeError):
        return ""


def _tags(values):
    return list(dict.fromkeys(value.strip() for value in values
                              if isinstance(value, str) and value.strip()))


def _statement_context(row):
    """Read structured attribution, never grade or interpret the owner's words."""
    source = row.get("source") or {}
    result = {
        "title": source.get("title") or row.get("technology") or row["text"][:80],
        "technologies": _tags(source["technology_tags"]) if isinstance(source.get("technology_tags"), list)
                        else _tags([row.get("technology", "")]),
        "project": source.get("project_name", row.get("project_name", "")),
    }
    if source.get("moment_id") and "technology_tags" not in source:
        # Older statements stored the tags as a display string. Recover them
        # only from the exact recorded moment, not by splitting arbitrary text.
        from .learning_moments import get
        from .errors import LedgerError
        try:
            moment, note = get(source["moment_id"])
            result.update(title=note["title"], technologies=_tags(note["technology_tags"]),
                          project=moment.get("project_name", ""))
        except (LedgerError, KeyError, TypeError, ValueError):
            pass
    return result


def _owner_plan(row):
    if row["kind"] == "skill_progress":
        return row.get("plan", "")
    if row["kind"] == "lesson":
        return row.get("choice", "")
    if row["kind"] == "statement" and profile.active(row):
        return (row.get("source") or {}).get("owner_state", "")
    return ""


def _bookmark(row):
    plan = _owner_plan(row)
    if plan not in ON_BOARD:
        return None
    item = {
        "record_id": row["id"], "source_kind": row["kind"], "observation": None,
        "title": row.get("title", ""), "technologies": _tags(row.get("technology_tags", [])),
        "project": row.get("project_name", ""), "plan": plan, "kind": None,
        "skill_id": None, "text": "", "date": _date(row.get("updated_at") or row.get("created_at")),
        "date_basis": "BOOKMARK_UPDATED", "authority": "OWNER_SELECTED_BOOKMARK",
    }
    if row["kind"] == "skill_progress":
        item.update(skill_id=row["asset_id"], text=row.get("note", ""),
                    kind=row.get("human") if row.get("human") in EXPERIENCE else None)
    elif row["kind"] == "lesson":
        item.update(technologies=_tags([row.get("technology", "")]),
                    text=next((feedback.get("text", "") for feedback in reversed(row.get("feedback", []))
                               if feedback.get("choice") == plan), "") or row.get("minimum_step", ""))
    else:
        item.update(_statement_context(row), text=row["text"])
    return item


def _entries(row):
    """Titles may be AI-proposed. The experience claim must be an owner record."""
    kind = row["kind"]
    common = {"record_id": row["id"], "source_kind": kind, "observation": None,
              "project": row.get("project_name", ""), "authority": "OWNER_SELF_REPORT_NOT_CERTIFICATION"}
    if kind == "skill_progress" and row.get("human") in EXPERIENCE:
        yield {**common, "title": row["title"], "technologies": _tags(row.get("technology_tags", [])),
               "kind": row["human"], "date": _date(row.get("updated_at")), "text": row.get("note", ""),
               "date_basis": "RECORD_UPDATED", "skill_id": row["asset_id"]}
    elif kind == "statement" and row.get("category") in ("experience", "understanding") and profile.active(row):
        state = (row.get("source") or {}).get("owner_state")
        if state and state not in EXPERIENCE:
            # Deferral, questions, reference and delegation are choices, not
            # experiences or evidence that the person did not understand.
            return
        yield {**common, **_statement_context(row), "kind": state or "SELF_REPORTED",
               "date": _date(row.get("updated_at") or row.get("created_at")), "text": row["text"],
               "date_basis": "RECORD_UPDATED", "skill_id": None,
               "provenance_status": (row.get("source") or {}).get("provenance_status")}
    elif kind == "lesson":
        for index, item in enumerate(row.get("feedback", [])):
            state = FEEDBACK.get(item.get("choice"))
            if state and item.get("text", "").strip():
                yield {**common, "title": row["title"], "technologies": _tags([row.get("technology", "")]),
                       "kind": state, "date": _date(item.get("recorded_at")), "text": item["text"],
                       "date_basis": "OWNER_ENTRY", "observation": index, "skill_id": None}


def _rows(db):
    if db is not None:
        for item in db.execute("SELECT document FROM records WHERE kind IN "
                               "('skill_progress','statement','lesson') ORDER BY updated DESC,id"):
            yield json.loads(item[0])


def _months(first, last):
    if not first or not last:
        return []
    end = int(last[:4]) * 12 + int(last[5:7]) - 1
    start = max(int(first[:4]) * 12 + int(first[5:7]) - 1, end - 17)
    return [str(index // 12).zfill(4) + "-" + str(index % 12 + 1).zfill(2)
            for index in range(start, end + 1)]


def snapshot(*, search="", technology="", kind="", project="", month="", offset=0, limit=24):
    profile.require(all(type(value) is str and len(value) <= 200 for value in
                        (search, technology, kind, project, month)), "ATLAS_FILTER")
    profile.require(kind in ("", *EXPERIENCE) and type(offset) is int and offset >= 0
                    and type(limit) is int and 1 <= limit <= 60, "ATLAS_PAGE")
    profile.require(not month or len(month) == 7 and month[:4].isdigit()
                    and month[4] == "-" and month[5:].isdigit() and 1 <= int(month[5:]) <= 12,
                    "ATLAS_MONTH")
    counts, technologies, projects, cells = Counter(), set(), set(), Counter()
    all_technologies, all_projects = set(), set()
    selected, bookmarks = [], []
    total, all_total, undated, bookmark_total = 0, 0, 0, 0
    first, last = "", ""
    policies = Counter()
    with profile.connection() as db:
        pref = profile._settings(db)
        stored_counts = (dict(db.execute("SELECT kind,COUNT(*) FROM records GROUP BY kind").fetchall())
                         if db is not None else {})
        revision = profile._meta(db, "revision", 0)
        for row in _rows(db):
            policies[_owner_plan(row)] += 1
            bookmark = _bookmark(row)
            if bookmark is not None:
                bookmark_total += 1
                if len(bookmarks) < 12:
                    bookmarks.append({key: value for key, value in bookmark.items() if key != "text"})
            for entry in _entries(row):
                all_total += 1
                all_technologies.update(entry["technologies"])
                if entry["project"]:
                    all_projects.add(entry["project"])
                if (technology and technology not in entry["technologies"]
                        or kind and entry["kind"] != kind
                        or project and entry["project"] != project
                        or month and entry["date"][:7] != month
                        or search and search.casefold() not in
                        " ".join([entry["title"], entry["text"], entry["project"], *entry["technologies"]]).casefold()):
                    continue
                total += 1
                counts[entry["kind"]] += 1
                technologies.update(entry["technologies"])
                if entry["project"]:
                    projects.add(entry["project"])
                if entry["date"]:
                    date = entry["date"][:7]
                    first = min(first, date) if first else date
                    last = max(last, date)
                    for tag in entry["technologies"] or [""]:
                        cells[(tag, date, entry["kind"])] += 1
                else:
                    undated += 1
                # Keep a bounded latest-page window; omitted records remain in the store.
                selected.append(entry)
                if len(selected) > offset + limit + 120:
                    selected.sort(key=lambda value: (value["date"], value["record_id"],
                                                    value["observation"] if value["observation"] is not None else -1),
                                  reverse=True)
                    del selected[offset + limit:]
    selected.sort(key=lambda value: (value["date"], value["record_id"],
                                    value["observation"] if value["observation"] is not None else -1), reverse=True)
    entries = [{key: value for key, value in entry.items() if key != "text"}
               | {"excerpt": entry["text"][:180]} for entry in selected[offset:offset + limit]]
    chart_months = _months(first, last)
    chart_tags = sorted({key[0] for key in cells}, key=str.casefold)[:12]
    chart = [{"technology": tag, "month": date, "kind": state, "count": count}
             for (tag, date, state), count in sorted(cells.items())
             if tag in chart_tags and date in chart_months]
    return {
        "format": "cleanroom.atlas.v1", "read_only": True, "model_calls": 0, "revision": revision,
        "read_at": datetime.now(timezone.utc).isoformat(), "personal_notebook_enabled": pref["enabled"],
        "summary": {"records": total, "all_records": all_total, "technologies": len(technologies),
                    "project_names": len(projects), "by_kind": dict(counts), "undated_records": undated,
                    "AI_procedure_drafts": stored_counts.get("skill_asset", 0),
                    "reference_choices": policies["REFERENCE"], "delegation_choices": policies["DELEGATE"]},
        "filters": {"search": search, "technology": technology, "kind": kind, "project": project, "month": month},
        "options": {"technologies": sorted(all_technologies, key=str.casefold)[:256],
                    "projects": sorted(all_projects, key=str.casefold)[:256],
                    "omitted_technologies": max(0, len(all_technologies) - 256),
                    "omitted_projects": max(0, len(all_projects) - 256)},
        "graph": {"months": chart_months, "technologies": chart_tags, "cells": chart,
                  "technology_limit": 12, "month_limit": 18,
                  "omitted_technology_rows": max(0, len({key[0] for key in cells}) - 12),
                  "older_months_present": bool(first and chart_months and first < chart_months[0]),
                  "multiple_tags_can_reference_the_same_record": True},
        "entries": entries, "offset": offset, "limit": limit, "has_more": offset + limit < total,
        "bookmarks": bookmarks, "bookmark_total": bookmark_total,
        "ability_score": None, "mastery_assessed": False,
    }


def detail(identity, observation=None):
    profile.require(type(identity) is str and 0 < len(identity) <= 200, "ATLAS_RECORD")
    profile.require(observation is None or type(observation) is int and 0 <= observation <= 1000000,
                    "ATLAS_OBSERVATION")
    with profile.connection() as db:
        row = profile._get(db, identity)
        profile.require(row is not None and row["kind"] in ("skill_progress", "statement", "lesson"),
                        "ATLAS_RECORD")
        entries = list(_entries(row))
        entry = next((item for item in entries if item["observation"] == observation), None)
        if entry is None and observation is None:
            entry = _bookmark(row)
        profile.require(entry is not None, "ATLAS_RECORD")
        result = {**entry, "read_only": True}
        if row["kind"] == "statement":
            result["provenance"] = row.get("source", {})
        elif row["kind"] == "lesson":
            result["provenance"] = {key: row.get(key) for key in
                                    ("project_name", "work_key", "source_event_ids", "previous_id")}
        if row["kind"] == "skill_progress":
            asset = profile._get(db, row["asset_id"])
            result.update(plan=row["plan"], ai_use=row["ai_use"], share_with_ai=row.get("share_with_ai", False))
            if asset and asset["kind"] == "skill_asset":
                result["procedure"] = asset["definition"]
                result["provenance"] = {key: asset.get(key) for key in
                                        ("project_name", "run_id", "source_ref", "model", "definition_sha256")}
        return result
