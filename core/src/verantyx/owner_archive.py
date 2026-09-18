"""Room-scoped, read-only history. Viewing never shares notes with a model."""
from .cleanroom_owner import catalogue, make_item, search
import hashlib


def conversation_items(snapshot, run_ids):
    allowed = set(run_ids)
    stamps = {event["project_id"] + ":" + event["event_id"]: event.get("recorded_at", "")
              for event in snapshot.get("events", [])}
    items = []
    for state in snapshot.get("states", []):
        run_id = state["run_id"]
        if run_id not in allowed or not state.get("work_session"):
            continue
        rows = catalogue({"state": state, "run_id": run_id, "revision": 0,
                          "human_decisions": list(state.get("human_decisions", {}).values())})
        reply = state.get("work_owner_reply")
        if reply:
            rows.append(make_item("request", reply["text"], reply["text"], run_id=run_id,
                                  source_ref=reply.get("source_ref"), revision=reply.get("revision")))
        owned = state.get("owner_experience", {})
        for field, kind in (("notes", "note"), ("decisions", "decision")):
            for row in owned.get(field, []):
                rows.append(make_item(kind, row.get("text") or row.get("statement"), row,
                                      run_id=run_id, source_ref=row.get("source_ref"), revision=row.get("revision")))
        for row in state.get("work_instructions", []):
            rows.append(make_item("request", row["user_text"], row["user_text"],
                                  run_id=run_id, source_ref=row.get("source_ref"), revision=row.get("revision")))
        answers = set()
        for turn in state.get("work_turns", []):
            for field, kind in (("answer", "response"), ("owner_question", "question")):
                body = turn["proposal"].get(field)
                if body:
                    rows.append(make_item(kind, body.splitlines()[0], body, run_id=run_id,
                                          source_ref=turn.get("source_ref"), revision=turn.get("revision")))
                    if field == "answer":
                        answers.add(body)
        result = state.get("work_result") or {}
        if result.get("answer") and result["answer"] not in answers:
            rows.append(make_item("response", result["answer"], result["answer"], run_id=run_id,
                                  source_ref=result.get("source_ref"), revision=result.get("revision")))
        for item in rows:
            item["created_at"] = stamps.get(item.get("source_ref"), stamps.get(state.get("request_ref"), ""))
        items.extend(rows)
    return items


def question_items(root, room):
    from .session_store import connection, root_key
    with connection() as store:
        if store is None or not store.execute("SELECT 1 FROM sqlite_master WHERE name='cr_insight_question'").fetchone():
            return []
        rows = store.execute("SELECT q.id,q.note_seq,q.question,q.answer,q.created_at,q.run_id FROM cr_insight_question q "
                             "JOIN cr_run r ON r.root=q.root AND r.run_id=q.run_id WHERE q.root=? AND r.room=?",
                             (root_key(root), room)).fetchall()
    items = []
    for identity, number, question, answer, stamp, run_id in rows:
        for kind, body in (("request", question), ("response", answer)):
            if body:
                item = make_item(kind, "L-" + str(number).zfill(6) + " " + body.splitlines()[0], body,
                                 run_id=run_id, source_ref="insight-question:" + identity)
                item["created_at"] = stamp
                items.append(item)
    return items


def page(root, room, snapshot, *, offset=0, limit=200, query="", history_cache=None):
    from .session_store import memo_index, memos_by_id, runs
    run_ids = runs(root, room=room)
    cache_key = (snapshot.get("project_revision"), room, tuple(run_ids))
    if history_cache is not None and history_cache.get("key") == cache_key:
        conversations = history_cache["items"]
    else:
        conversations = conversation_items(snapshot, run_ids)
        if history_cache is not None:
            history_cache.update(key=cache_key, items=conversations)
    history = search([*conversations, *question_items(root, room)], query)
    notes = memo_index(root, room, query=query)
    # Only materialize memo bodies on the selected page. All source records stay intact.
    index = [(row.get("created_at", ""), row["id"], "conversation", row) for row in history]
    index.extend((row["created_at"], row["id"], "memo", row) for row in notes)
    index.sort(key=lambda row: (row[0], row[1]), reverse=True)
    limit = min(200, max(1, limit))
    offset = min(max(0, offset), ((len(index) - 1) // limit) * limit if index else 0)
    selected = index[offset:offset + limit]
    memos = {row["id"]: row for row in memos_by_id(root, room, [row[1] for row in selected if row[2] == "memo"])}
    items = []
    for _, identity, kind, row in selected:
        if kind == "memo":
            note = memos.get(identity)
            if note is None:
                continue
            row = make_item("note", note["body"].splitlines()[0], note["body"],
                            source_ref="owner-note:" + identity, run_id=note.get("run_id"),
                            revision=hashlib.sha256(note["body"].encode("utf-8")).hexdigest())
            row["created_at"] = note["created_at"]
        items.append(row)
    return {"items": items, "total": len(index), "offset": offset, "limit": limit,
            "query": query, "conversations": len(history), "memos": len(notes), "room": room}
