"""Read-only six-delta ownership report for one recorded work item."""

COMMANDS = {"ownership"}


def register(sub):
    parser = sub.add_parser("ownership", add_help=False, allow_abbrev=False)
    parser.add_argument("run_id")


def dispatch(root, configuration, args, locale):
    from .ownership_report import report
    return report(root, configuration, args.run_id, locale)


def display(result, locale, command):
    from .ownership_report import display as show
    show(result, locale, command)
