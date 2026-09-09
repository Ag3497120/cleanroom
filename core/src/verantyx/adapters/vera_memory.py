"""Fixed MCP stdio operations for an explicitly named Vera memory.

No dependency on a model SDK or the MCP Python SDK is needed in the client.
The configured server is trusted local code and must implement MCP stdio.
"""
import re

from .command_process import BoundedProcess
from ..domain.codec import decode
from ..errors import LedgerError

READ_TOOLS = {"start": "vera_session_start", "read": "vera_read", "search": "vera_search",
              "lookup": "vera_lookup", "digest-lookup": "vera_digest_lookup"}


def memory_name(name):
    if type(name) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise LedgerError("MEMORY_NAME_REQUIRED")
    return name


class VeraMemory:
    def __init__(self, command, name, *, timeout=30, max_output=1024 * 1024):
        self.name = memory_name(name)
        self.transport = BoundedProcess(command, timeout=timeout, max_output=max_output)
        self.next_id = 0

    def __enter__(self):
        self.transport.__enter__()
        try:
            result = self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                              "clientInfo": {"name": "verantyx", "version": "1"}})
            if (type(result) is not dict or result.get("protocolVersion") not in
                    ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")):
                raise LedgerError("BRIDGE_PROTOCOL")
            self.transport.send_json({"jsonrpc": "2.0", "method": "notifications/initialized"})
            return self
        except BaseException:
            self.transport.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        self.transport.__exit__(*args)

    def _rpc(self, method, params):
        self.next_id += 1
        expected = self.next_id
        self.transport.send_json({"jsonrpc": "2.0", "id": expected, "method": method, "params": params})
        for _ in range(65):
            reply = self.transport.receive_json()
            if type(reply) is not dict or reply.get("jsonrpc") != "2.0":
                raise LedgerError("BRIDGE_PROTOCOL")
            if "id" not in reply and type(reply.get("method")) is str:
                continue
            if reply.get("id") != expected or "method" in reply:
                raise LedgerError("BRIDGE_PROTOCOL")
            if "error" in reply:
                raise LedgerError("MEMORY_REMOTE_ERROR")
            if "result" not in reply:
                raise LedgerError("BRIDGE_PROTOCOL")
            return reply["result"]
        raise LedgerError("BRIDGE_PROTOCOL")

    def _tool(self, tool, arguments):
        result = self._rpc("tools/call", {"name": tool, "arguments": {**arguments, "name": self.name}})
        if type(result) is not dict or result.get("isError") or type(result.get("content")) is not list:
            raise LedgerError("MEMORY_REMOTE_ERROR")
        text = []
        for item in result["content"]:
            if type(item) is not dict or item.get("type") != "text" or type(item.get("text")) is not str:
                raise LedgerError("BRIDGE_PROTOCOL")
            text.append(item["text"])
        raw = "\n".join(text)
        if tool == "vera_session_start":
            return raw
        value = decode(raw)
        if type(value) is dict and "error" in value:
            raise LedgerError("MEMORY_REMOTE_ERROR")
        return value

    def read(self, operation, **arguments):
        if operation not in READ_TOOLS:
            raise LedgerError("ARGUMENTS")
        expected = {"start": {"lang", "max_chars"}, "read": {"after_n", "limit", "max_chars"},
                    "search": {"query", "k"}, "lookup": {"n"}, "digest-lookup": {"digest_id"}}[operation]
        if not set(arguments) <= expected:
            raise LedgerError("ARGUMENTS")
        return self._tool(READ_TOOLS[operation], arguments)

    def save_packet(self, fields):
        if type(fields) is not dict or set(fields) != {"request", "change", "reason", "files", "result",
                                                       "interpretation", "unresolved", "lang", "model_timestamp", "author"}:
            raise LedgerError("MEMORY_PACKET_INVALID")
        result = self._tool("vera_record", fields)
        if (type(result) is not dict or type(result.get("turn_id")) is not str or
                result.get("memory", {}).get("name") != self.name):
            raise LedgerError("BRIDGE_PROTOCOL")
        return result
