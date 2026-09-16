"""Owner-only personal notebook commands, independent of project execution grants."""
import json
import sys

from . import personal_profile as profile
from .errors import LedgerError

COMMANDS = ("my-profile", "my-journal", "my-portfolio", "my-skills", "web", "atlas", "my-learning")


def register(sub):
    web = sub.add_parser("web", aliases=["atlas"],
                         help="Open your read-only personal experience map")
    web.add_argument("--port", type=int, default=0,
                     help="Loopback port; 0 selects an available port")
    web.add_argument("--no-open", action="store_true",
                     help="Print the private local URL without opening a browser")
    learning = sub.add_parser("my-learning", help="Unpack skills and technologies from recorded implementation")
    learning.add_argument("action", nargs="?", default="menu", choices=("menu", "list", "topics", "show", "unpack", "index", "moments", "record"))
    learning.add_argument("--id")
    learning.add_argument("--skill")
    learning.add_argument("--technology", default="")
    learning.add_argument("--run")
    learning.add_argument("--page", type=int, default=0)
    learning.add_argument("--detail", choices=("summary", "full", "sources"), default="summary")
    learning.add_argument("--send", action="store_true")
    learning.add_argument("--query", action="append", default=[])
    learning.add_argument("--web", action="store_true")
    learning.add_argument("--search-adapter")
    learning.add_argument("--trust-search-adapter", action="store_true")
    learning.add_argument("--key")
    learning.add_argument("--yes", action="store_true")
    learning.add_argument("--moment")
    learning.add_argument("--state", choices=("EXPLAINED", "APPLIED", "STILL_EXPLORING", "NEXT_TIME", "REFERENCE", "DELEGATE"))
    learning.add_argument("--text", default="")
    learning.add_argument("--share", action="store_true")
    from .skill_assets import PLANS, HUMAN, AI_USE
    skill = sub.add_parser("my-skills", help="AI procedure drafts and your voluntary skill board")
    skill.add_argument("action", nargs="?", default="menu",
                       choices=("menu", "show", "board", "choose", "history", "sync", "quiet", "export", "unpack"))
    skill.add_argument("--id")
    skill.add_argument("--page", type=int, default=0)
    skill.add_argument("--search", default="")
    skill.add_argument("--plan", choices=PLANS)
    skill.add_argument("--human", choices=HUMAN)
    skill.add_argument("--ai-use", choices=AI_USE)
    skill.add_argument("--text", default="")
    skill.add_argument("--share", choices=("yes", "no"))
    skill.add_argument("--scope", choices=("SESSION", "TODAY", "GLOBAL"), default="SESSION")
    skill.add_argument("--select", action="append", default=[])
    skill.add_argument("--output")
    skill.add_argument("--yes", action="store_true")
    parser = sub.add_parser("my-profile", help="Personal experience across projects; no ability scoring")
    parser.add_argument("action", nargs="?", default="menu",
                        choices=("menu", "show", "set", "pace", "talk", "export", "import", "forget",
                                 "accept", "dismiss", "enable", "pause"))
    parser.add_argument("--text")
    parser.add_argument("--technology", default="")
    parser.add_argument("--kind", choices=profile.KINDS, default="experience")
    parser.add_argument("--scope", choices=("GLOBAL", "SESSION", "TODAY"), default="GLOBAL")
    parser.add_argument("--shared-with-ai", action="store_true")
    parser.add_argument("--id")
    parser.add_argument("--output")
    parser.add_argument("--input")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--include-private", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--mode", choices=profile.ENUMS["mode"])
    parser.add_argument("--weight", choices=profile.ENUMS["weight"])
    parser.add_argument("--timing", choices=profile.ENUMS["timing"])
    parser.add_argument("--daily-limit", type=int)
    parser.add_argument("--per-work", type=int)
    parser.add_argument("--share-context", choices=("yes", "no"))
    parser.add_argument("--stack-questions", choices=("yes", "no"))

    journal = sub.add_parser("my-journal", help="Actual work, AI interpretations and your own words")
    journal.add_argument("action", nargs="?", default="menu", choices=("menu", "show", "note", "choose"))
    journal.add_argument("--id")
    journal.add_argument("--text")
    journal.add_argument("--choice", choices=sorted(profile.CHOICES))
    journal.add_argument("--shared-with-ai", action="store_true")

    portfolio = sub.add_parser("my-portfolio", help="Explicitly selected AI-assisted experience; never auto-publish")
    portfolio.add_argument("--journal", action="append", default=[])
    portfolio.add_argument("--experience", action="append", default=[])
    portfolio.add_argument("--description", default="")
    portfolio.add_argument("--output")


def dispatch(root, configuration, args, *, as_json=False, locale=None):
    if args.command in ("web", "atlas"):
        from .atlas_server import serve
        return serve(port=args.port, open_browser=not args.no_open,
                     locale=locale or (configuration or {}).get("ui", {}).get("locale", "ja"),
                     as_json=as_json,
                     project_root=root if configuration is not None and not getattr(args, "locale_override", False) else None)
    from . import personal_console as ui
    from . import personal_growth as growth
    interactive = sys.stdin.isatty() and sys.stdout.isatty() and not as_json
    if args.command == "my-learning":
        from . import learning_guides as guides
        from . import learning_capture as capture
        from . import learning_console
        if args.action == "moments":
            from .learning_moments import entries, menu
            if interactive:
                menu(root, configuration)
                return {"status": "CLOSED"}
            return {"items": entries(args.run), "human_mastery_inferred": False}
        if args.action == "record":
            from .learning_moments import record_understanding
            profile.require(args.moment and args.state and args.text and args.yes, "OWNER_WORDS_REQUIRED")
            return record_understanding(args.moment, args.state, args.text, share=args.share)
        if args.action == "menu" and interactive:
            learning_console.menu(root, configuration)
            return {"ok": True, "status": "CLOSED"}
        if args.action in ("list", "menu"):
            return guides.catalogue(offset=args.page * 24)
        if args.action == "topics":
            return {"topics": capture.topics(), "ability_inference": False}
        if args.action == "show":
            profile.require(args.id, "LEARNING_GUIDE_REQUIRED")
            if interactive:
                learning_console.show(args.id, args.detail)
                return {"ok": True, "status": "CLOSED"}
            return guides.read(args.id, detail=args.detail)
        if args.action == "index":
            profile.require(configuration is not None and args.run and args.yes, "LEARNING_INDEX_APPROVAL_REQUIRED")
            return capture.index_project(root, configuration, args.run)
        if args.action == "unpack":
            if interactive and not args.send:
                learning_console.unpack(root, configuration, skill_id=args.skill,
                                        technology=args.technology, run_id=args.run, moment_id=args.moment)
                return {"ok": True, "status": "CLOSED"}
            profile.require(configuration is not None and args.send, "LEARNING_SEND_APPROVAL_REQUIRED")
            from . import development_console as console
            return console._mutate(root, configuration, guides.create, skill_id=args.skill,
                technology=args.technology, run_id=args.run, moment_id=args.moment, page=args.page, send=args.send,
                queries=args.query, approve_web=args.web, search_adapter=args.search_adapter,
                trust_search=args.trust_search_adapter, key=args.key)
    if args.command == "my-skills":
        from . import skill_assets as skills
        from . import skill_console
        if args.action == "unpack":
            profile.require(args.id and interactive, "INTERACTIVE_SKILL_UNPACK_REQUIRED")
            from .learning_console import unpack
            unpack(root, configuration, skill_id=args.id)
            return {"ok": True, "status": "CLOSED"}
        if args.action == "menu" and interactive:
            skill_console.menu(root, configuration)
            return {"ok": True, "status": "CLOSED"}
        if args.action in ("show", "menu"):
            if args.id:
                asset = skills.resolve(args.id, root, configuration)
                with profile.connection() as db:
                    return {"asset": asset, "progress": skills._progress(db, asset)}
            return skills.catalogue(root, configuration, page=args.page, search=args.search)
        if args.action == "board":
            return skills.board(page=args.page)
        if args.action == "history":
            profile.require(args.id, "SKILL_REQUIRED")
            return {"items": skills.history(args.id, page=args.page)}
        if args.action == "choose":
            profile.require(args.id, "SKILL_REQUIRED")
            asset = skills.resolve(args.id, root, configuration)
            return skills.choose(asset, plan=args.plan, human=args.human, ai_use=args.ai_use,
                                 note=args.text, share=None if args.share is None else args.share == "yes")
        if args.action == "quiet":
            return {"settings": profile.configure(
                {"onboarded": True, "mode": "on_demand", "timing": "on_demand", "stack_questions": False},
                scope=args.scope), "host_tool_permissions_changed": False}
        if args.action == "sync":
            profile.require(configuration is not None and args.yes, "SKILL_INDEX_APPROVAL_REQUIRED")
            return skills.sync_project(root, configuration)
        if args.action == "export":
            value = skills.portfolio(args.select or ([args.id] if args.id else []))
            return {"path": ui.write_export(args.output, value), "published": False} if args.output else value
        raise LedgerError("ARGUMENTS")
    if args.command == "my-portfolio":
        if interactive and not args.journal and not args.experience and not args.output:
            ui.portfolio_menu()
            return {"ok": True, "status": "CLOSED"}
        value = growth.portfolio(args.journal, personal_summary=args.description, experience_ids=args.experience)
        if args.output:
            return {"ok": True, "path": ui.write_export(args.output, value), "published": False}
        return value
    if args.command == "my-journal":
        if args.action == "menu" and interactive:
            ui.journal(root, configuration)
            return {"ok": True, "status": "CLOSED"}
        if args.action in ("show", "menu"):
            if args.id:
                value = profile.get_record(args.id)
                profile.require(value is not None, "PERSONAL_RECORD_REQUIRED")
                return value
            return {"journals": profile.records("journal", 300), "lessons": profile.records("lesson", 300)}
        if args.action == "note":
            profile.require(args.id and args.text, "PERSONAL_NOTE_ARGUMENTS")
            return profile.add_note(args.text, journal_id=args.id, share=args.shared_with_ai)
        profile.require(args.id and args.choice, "PERSONAL_CHOICE_ARGUMENTS")
        return profile.choose_lesson(args.id, args.choice, text=args.text or "",
                                     share=True if args.shared_with_ai else None)
    action = args.action
    if action == "menu" and interactive:
        ui.menu(root, configuration)
        return {"ok": True, "status": "CLOSED"}
    if action in ("menu", "show"):
        return profile.snapshot()
    if action == "set":
        profile.require(args.text, "PERSONAL_STATEMENT_REQUIRED")
        return profile.statement(args.text, technology=args.technology, kind=args.kind,
                                 scope=args.scope, share=args.shared_with_ai, record_id=args.id)
    if action == "pace":
        fields = {name: getattr(args, name) for name in
                  ("mode", "weight", "timing", "daily_limit", "per_work")
                  if getattr(args, name) is not None}
        if args.share_context is not None:
            fields["share_with_ai"] = args.share_context == "yes"
        if args.stack_questions is not None:
            fields["stack_questions"] = args.stack_questions == "yes"
        if not fields and interactive:
            ui.pace(root, configuration)
            return {"ok": True, "settings": profile.preferences()}
        profile.require(fields, "PERSONAL_PREFERENCE_REQUIRED")
        return {"settings": profile.configure(fields, scope=args.scope)}
    if action in ("enable", "pause"):
        return {"settings": profile.configure({"onboarded": True, "enabled": action == "enable"})}
    if action == "talk":
        if not args.text and interactive:
            return ui.talk(root, configuration) or {"ok": True, "status": "CANCELLED"}
        profile.require(args.text and args.send and configuration is not None, "PERSONAL_SEND_APPROVAL_REQUIRED")
        from . import development_console as console
        return console._mutate(root, configuration, growth.converse, args.text)
    if action == "export":
        profile.require(args.include_private and args.output, "PRIVATE_EXPORT_APPROVAL_REQUIRED")
        return {"ok": True, "path": ui.write_export(args.output, profile.export_bundle()),
                "contains_private_data": True}
    if action == "import":
        profile.require(args.input and args.yes, "PERSONAL_IMPORT_APPROVAL_REQUIRED")
        from .adapters.observations import read_document
        return profile.import_bundle(json.loads(read_document(args.input, 8 * 1024 * 1024)))
    if action == "forget":
        profile.require(args.id and args.yes, "PERSONAL_DELETE_APPROVAL_REQUIRED")
        return profile.forget(args.id)
    if action in ("accept", "dismiss"):
        profile.require(args.id and args.yes, "PERSONAL_OWNER_APPROVAL_REQUIRED")
        if action == "accept":
            return growth.accept_update(args.id, share=args.shared_with_ai, scope=args.scope)
        return growth.reject_update(args.id)
    raise LedgerError("ARGUMENTS")
