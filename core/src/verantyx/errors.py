"""Stable errors shared by storage, the kernel, and the CLI."""


class LedgerError(Exception):
    def __init__(self, code, details=None):
        self.code = code
        self.details = details or {}
        super().__init__(code)
