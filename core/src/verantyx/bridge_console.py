"""Optional notebook integrations, kept out of the normal work entrance."""
from . import notebook_bridge as bridge


def menu(root, configuration):
    from . import development_console as ui
    from .agent_console import terminal_text
    while True:
        action = ui._pick("Notebook connections", ["local", "obsidian", "sync", "import", "moments", "roles", "mcp"],
                          lambda v: {"local": "Local / keep Cleanroom only", "obsidian": "Start with Obsidian",
                                     "sync": "Export current records to the connected vault",
                                     "import": "Import another agent's SKILL.md / text",
                                     "moments": "During work / my own understanding", "roles": "Parent / child models",
                                     "mcp": "Connect another agent through MCP"}[v])
        if action is None:
            return
        if action == "local":
            value = bridge.settings()
            if value.get("id"):
                from . import personal_profile as profile
                profile.put_record({**value, "enabled": False, "auto_sync": False})
        elif action == "obsidian":
            print("A vault can be cloud-synced by Obsidian or another app. Private records will be exported.")
            path = ui._ask("Absolute vault directory / an empty folder can start a new notebook")
            if path and ui._start("Export private records here, including future implementation notes?"):
                print(terminal_text(str(bridge.connect(path, confirmed=True, include_private=True, auto=True))))
        elif action == "sync":
            if ui._start("Export current private records to your selected vault?"):
                print(terminal_text(str(bridge.sync())))
        elif action == "import":
            path = ui._ask("Absolute path to SKILL.md or a Markdown/text procedure")
            if not path:
                continue
            title = ui._ask("Title", "Imported skill")
            origin = ui._ask("Source agent / provenance", "Owner-selected file")
            if ui._start("Import as an unverified procedure, without running it or marking it learned?"):
                result = bridge.import_file(path, origin=origin, title=title, confirmed=True)
                print(terminal_text(str(result)))
                print("My skills lets you separately choose reference, delegation or your own experience.")
        elif action == "mcp":
            print("Install the optional transport: python -m pip install -e './core[mcp]'")
            print("MCP stdio command: verantyx --project /absolute/project mcp")
            print("--allow-personal grants private notebook reads; --allow-import grants passive report/skill imports.")
            print("No tool grants mastery, permissions, arbitrary shell access or active rules.")
        elif action == "moments":
            from .learning_moments import menu as moments_menu
            moments_menu(root, configuration)
        else:
            from .model_roles import menu as roles_menu
            roles_menu(root, configuration)
