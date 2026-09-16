# Cleanroom: CLI mainline and optional macOS interface

## Product boundary

The standalone CLI remains the primary product. The macOS application is a
client of the same installed CLI, not a second Vera kernel or model runtime.

- Work, model selection, provider authentication, reflection, permissions and
  ledger transitions stay in the CLI.
- The macOS interface renders CLI projections and sends explicit user requests.
- Private notes use the CLI's existing local Owner notebook. They are only sent
  to AI if the user explicitly selects them as request references.
- AI suggestions do not become human decisions, active rules, verified tests or
  confirmed understanding merely because they appear in the app.
- The existing IDE remains accessible through the "IDE tools" tab. Its old
  AgentLoop and settings are not the Cleanroom execution path.

## Prepare the standalone CLI

From the current CLI repository, activate the Python 3.11+ environment you use
for the CLI, then install the updated source:

~~~sh
python -m pip install -e ./core
command -v verantyx
verantyx --project /absolute/path/to/your-project setup models
~~~

The normal commands and terminal UI remain available:

~~~sh
verantyx --project /absolute/path/to/your-project
verantyx --project /absolute/path/to/your-project "Your task"
~~~

The new machine-facing command is verantyx desktop-bridge. It reads one JSON
request from stdin, writes one JSON response to stdout, and exits. It is not an
HTTP server and must not be exposed as a remote or model-authorized control API.

## macOS interface

The IDE source is based on Verantyx commit
bdcd218177430a492375ecdc1675598cda623801. The existing Xcode application target
includes CleanroomCLIClient.swift and CleanroomWorkbenchView.swift.

1. Open Verantyx.xcodeproj in Xcode on macOS.
2. Build/run the existing Verantyx application target.
3. In Cleanroom, choose the verantyx executable reported by command -v.
4. Choose the same project directory that you use with the CLI.
5. Connect. If this is a new project, explicitly choose "Initialize project".
6. Enter a task and review the sending scope before starting.

The app does not bundle or install Python in this first integration. A selected
CLI executable from an existing virtual environment is required. An optional
CLEANROOM_CLI_EXECUTABLE environment variable can supply its path.

## Implemented integration surface

- Native Agent/Owner split view inside the existing IDE.
- New work, continued work, saved history, and separate work/reflection states.
- Periodic read-only snapshots from the CLI's local ledger.
- Private memo input, local search, reference cards and explicit quoted-context
  selection using the same revision-bound Owner references as the CLI.
- Empty Enter cycles Agent input, memo input, note search and Agent input.
- Models and the full terminal UI open the same executable in Terminal.
- Candidate folders can be revealed without adopting files or running them.
- A stop request interrupts the owned CLI invocation; the CLI propagates it to
  its descendants. It does not erase records or automatically retry work.
- The bridge does not expose arbitrary argv, shell execution, publication,
  adoption or rule activation.

The native suggestion buttons are the first UI integration, not complete
keyboard-completion parity with the terminal UI. Final Owner choices, mastery
evidence, adoption and advanced settings remain available through "Review in
CLI" / "CLI". Browser preview and legacy IDE tool receipts are not wired into
the current Work Agent yet.

## Legacy IDE services

Cleanroom startup does not run the old IDE bootstrap sequence that starts MCP,
extension hosts, memory model loading or screen-control permission prompts.

For deliberate legacy-IDE development, add --legacy-ide-services to the Xcode
scheme's launch arguments. This is opt-in: those old services retain the
limitations documented during the source assessment, including the old MCP
launcher. They are not required for Cleanroom and are not automatically granted
access to the CLI ledger or classified as verified execution evidence.

## Protocol contract

~~~json
{
  "protocol": "cleanroom.desktop.v1",
  "request_id": "0123456789abcdef0123456789abcdef",
  "action": "snapshot",
  "project": "/absolute/path/to/project"
}
~~~

Supported actions: hello, snapshot, initialize, work, organize, memo.

Work accepts text, optional run_id for continuation, include, and up to eight
reference_ids. Work and organize require send_confirmed: true.
The request ID also supplies the existing CLI idempotency key. No mutation is
automatically retried after a transport failure.

Responses distinguish transport success and the CLI exit code. The UI must
also retain the separate WorkResult and ReflectionResult states from the
ledger. A broken connection is not proof that the work failed or never ran.

## Implementation status and next integration steps

This change adds source integration only. It has not been built, launched or
end-to-end tested as part of this change. It is not a signed/notarized macOS
release, and a functioning legacy IDE build is not asserted.

Next:
1. Build and run the native interface against the same CLI used in Terminal.
2. Exercise one task, continuation, a private memo, and a failed reflection.
3. Connect selected legacy browser/process helpers behind current CLI authority
   and typed execution receipts, without restoring keyword-based routing.
4. Add native Owner decisions and adoption through existing CLI authority APIs.
5. Bundle a versioned runtime, then signing, notarization and update delivery.

Do not mark tests as passed, human understanding as confirmed, or the macOS
release as complete until the corresponding evidence exists.

