"""Implementation-time explanations and explicit owner statements, never inferred ability."""
from . import personal_profile as profile
from . import learning_capture as capture
from .domain.codec import canonical
from copy import deepcopy


def entries(run_id=None, limit=100):
    rows = capture.traces()
    known = {row["event"]["source_ref"] for row in rows}
    result = []
    for row in rows:
        if run_id and row["run_id"] != run_id:
            continue
        notes, _ = capture.notes_from_event(row["event"], known)
        indexed = [(str(index), note) for index, note in enumerate(notes)]
        indexed += [("pending-" + str(item["index"]), item["note"])
                    for item in capture.pending_notes_from_event(row["event"], known)]
        for index, note in indexed:
            result.append({"id": row["id"] + ":" + str(index), "record_id": row["id"],
                           "title": note["title"], "note": note, "run_id": row["run_id"],
                           "provenance_status": note.get("provenance_status", "SOURCE_LINKED"),
                           "work_key": row["work_key"], "source_ref": row["event"]["source_ref"],
                           "profile_version": row.get("profile_snapshot_sha256"),
                           "authority": "AI_EXPLANATION_NOT_HUMAN_MASTERY"})
    return list(reversed(result))[:limit]


def get(identity):
    profile.require(type(identity) is str and ":" in identity, "LEARNING_MOMENT_REQUIRED")
    record_id, index = identity.rsplit(":", 1)
    row = profile.get_record(record_id)
    profile.require(row and row["kind"] == "learning_trace", "LEARNING_MOMENT_REQUIRED")
    known = {r["event"]["source_ref"] for r in capture.traces()}
    if index.startswith("pending-") and index[8:].isdecimal():
        raw_index = int(index[8:])
        for item in capture.pending_notes_from_event(row["event"], known):
            if item["index"] == raw_index:
                return row, item["note"]
        # A later source can resolve a previously pending reference. Keep the
        # pending ID addressable, but do not change or rewrite its original event.
        raw = row["event"].get("payload", {}).get("proposal", {}).get("learning_notes", [])
        profile.require(isinstance(raw, list) and raw_index < len(raw), "LEARNING_MOMENT_REQUIRED")
        single = deepcopy(row["event"])
        single["payload"]["proposal"]["learning_notes"] = [raw[raw_index]]
        notes, errors = capture.notes_from_event(single, known)
        profile.require(notes and not errors, "LEARNING_MOMENT_REQUIRED")
        return row, notes[0]
    profile.require(index.isdecimal(), "LEARNING_MOMENT_REQUIRED")
    notes, _ = capture.notes_from_event(row["event"], known)
    profile.require(int(index) < len(notes), "LEARNING_MOMENT_REQUIRED")
    return row, notes[int(index)]


def record_understanding(identity, state, text, *, share=False):
    profile.require(state in ("EXPLAINED", "APPLIED", "STILL_EXPLORING", "NEXT_TIME", "REFERENCE", "DELEGATE"),
                    "LEARNING_OWNER_STATE")
    profile.require(type(text) is str and bool(text.strip()), "OWNER_WORDS_REQUIRED")
    row, note = get(identity)
    result = profile.statement(text, technology=", ".join(note["technology_tags"])[:160],
                               kind="understanding", share=share,
                               source={"moment_id": identity, "source_ref": row["event"]["source_ref"],
                                       "owner_state": state, "authority": "EXPLICIT_SELF_REPORT",
                                       "technology_tags": list(note["technology_tags"]), "title": note["title"],
                                       "project_name": row.get("project_name", ""), "work_key": row["work_key"],
                                       "provenance_status": note.get("provenance_status", "SOURCE_LINKED")})
    from .notebook_bridge import auto_sync
    auto_sync()
    return result


def menu(root, configuration):
    from . import development_console as ui
    from .learning_console import line, unpack
    while True:
        moment = ui._pick("During work / 実装中に残した説明", entries(),
                          lambda row: row["title"] + (" [Source review pending / 出典確認待ち]"
                          if row["provenance_status"] == "PENDING_SOURCE_REVIEW" else ""))
        if moment is None:
            return
        row, note = get(moment["id"])
        if note.get("provenance_status") == "PENDING_SOURCE_REVIEW":
            line("Source review pending / 出典確認待ち。元の説明は保存済みで、作業結果は変わりません。")
            line("Unpack reads the original work trace; it does not approve or rewrite this note.")
        line(canonical(note))
        action = ui._pick("Your choice / 記録がないことは能力不足ではありません",
                          ["read", "record", "back"],
                          lambda v: {"read": "Unpack this recorded work / 元の仕事から詳しく読む",
                                     "record": "My own words / 今の理解・次回の希望を残す", "back": "Back"}[v])
        if action == "read":
            unpack(root, configuration, moment_id=moment["id"])
        elif action == "record":
            state = ui._pick("What do you want to record?",
                             ["EXPLAINED", "APPLIED", "STILL_EXPLORING", "NEXT_TIME", "REFERENCE", "DELEGATE"],
                             lambda value: {"EXPLAINED": "I can explain this / 自分の言葉で説明",
                                            "APPLIED": "I used this / 使った経験",
                                            "STILL_EXPLORING": "Still exploring / 今の疑問を残す",
                                            "NEXT_TIME": "Another time / 次の機会に",
                                            "REFERENCE": "Keep as reference / 参照できれば十分",
                                            "DELEGATE": "Let AI handle this / 委譲して進める"}[value])
            if state:
                text = ui._ask("Your words / 空欄なら記録しない")
                if text:
                    record_understanding(moment["id"], state, text)
