"""Explicit review, conflict resolution, verification and permission for canonical integration."""
COMMANDS = {'integration-' + name for name in ('plan', 'review', 'resolve', 'verify', 'authorize', 'apply')}


def register(sub):
    for name in sorted(COMMANDS):
        parser = sub.add_parser(name, add_help=False, allow_abbrev=False)
        parser.add_argument('run_id')
        if name != 'integration-review':
            parser.add_argument('--key', required=True)
            parser.add_argument('--precedent', required=True)
        if name == 'integration-plan':
            parser.add_argument('--adoption', required=True)
            parser.add_argument('--branch', required=True)
            parser.add_argument('--mode', choices=('merge', 'rebase'), default='merge')
            parser.add_argument('--message', default='Integrate adopted Vera change')
        else:
            parser.add_argument('--integration', required=True)
        if name == 'integration-resolve':
            parser.add_argument('--files', required=True)
            parser.add_argument('--reason', required=True)
        if name == 'integration-authorize':
            parser.add_argument('--reason', required=True)
            parser.add_argument('--ttl', type=int, default=300)


def dispatch(root, cfg, args, locale=None):
    from . import integration as api
    if args.command == 'integration-plan':
        return api.plan_integration(root, cfg, args.run_id, args.adoption, args.precedent, args.key,
                                    branch=args.branch, mode=args.mode, message=args.message)
    if args.command == 'integration-review':
        return api.review_integration(root, cfg, args.run_id, args.integration)
    values = (root, cfg, args.run_id, args.integration, args.precedent, args.key)
    if args.command == 'integration-resolve':
        from .adapters.observations import read_document
        from .domain.codec import decode
        return api.resolve_integration(*values, files=decode(read_document(args.files)), reason=args.reason)
    if args.command == 'integration-verify':
        return api.check_integration(*values)
    if args.command == 'integration-authorize':
        return api.authorize_integration(*values, reason=args.reason, ttl=args.ttl)
    return api.apply_integration(*values)


def display(result, locale, command):
    from .i18n import text
    from .cli import visible
    item = result['integration']
    print(text(locale, 'integration.title'))
    print(result['integration_id'] + ': ' + item['status'])
    print(visible(item['plan']['target_ref']))
    for name in item['conflicts']:
        print(text(locale, 'integration.conflict', path=visible(name)))
    if item.get('receipt'): print(item['receipt']['commit'])
    print(text(locale, 'integration.boundary'))
