"""Closed CLI extension registry; mutation commands share the authority gate."""


def modules():
    from . import commands_jobs, commands_verification, commands_governance, commands_learning, commands_integration
    from . import commands_authority, commands_oracles, commands_command_effects, commands_connections
    from . import commands_response, commands_context, commands_workflow, commands_capture, commands_work
    return (commands_jobs, commands_verification, commands_governance, commands_learning, commands_integration,
            commands_authority, commands_oracles, commands_command_effects, commands_connections, commands_response, commands_context,
            commands_workflow, commands_capture, commands_work)


def register(sub):
    for module in modules():
        module.register(sub)


def handler(command):
    return next((module for module in modules() if command in module.COMMANDS), None)
