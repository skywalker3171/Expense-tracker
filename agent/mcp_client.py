"""
mcp_client.py — local shim that calls the three MCP servers via stdio JSON-RPC.

In production (Code Engine) this module is replaced by the runtime-injected client.
Locally it spawns the MCP server process ONCE per server key and reuses it for all
calls in the same process — avoids the 10-15s npx startup cost on every tool call.

Usage:
    from mcp_client import call_tool
    result = call_tool("search_emails", query="subject:Expense")

Environment variables (all already in secrets.env):
    MCP_MODE=mock       → return canned responses (unit tests, no live services needed)
    MCP_MODE=real       → spawn real MCP server processes (default)
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
import atexit
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool → server routing
# ---------------------------------------------------------------------------

# Explicit tool → server mapping (Gmail MCP tools have no shared prefix)
_GMAIL_TOOLS = {
    "send_email", "draft_email", "read_email", "search_emails",
    "modify_email", "delete_email", "list_email_labels",
    "batch_modify_emails", "batch_delete_emails",
    "create_label", "update_label", "delete_label", "get_or_create_label",
    "create_filter", "list_filters", "get_filter", "delete_filter",
    "create_filter_from_template", "download_attachment",
}

# Explicit Cloudant tool names (no shared prefix with other servers)
_CLOUDANT_TOOLS = {
    "get_server_info", "list_databases", "create_database", "delete_database",
    "get_database_info", "get_document", "create_document", "update_document",
    "delete_document", "list_documents", "mango_query", "create_index", "list_indexes",
}

_TOOL_SERVER_MAP = {
    # COS / S3 MCP (aws-s3-mcp) — prefix match
    "s3_": "s3",
}


# ---------------------------------------------------------------------------
# Exe resolver — handles Windows .cmd wrappers
# ---------------------------------------------------------------------------

def _resolve_exe(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise FileNotFoundError(
            f"'{name}' not found on PATH. Make sure Node.js is installed."
        )
    return resolved


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------

_rpc_id_lock = threading.Lock()
_rpc_id = 0


def _next_id() -> int:
    global _rpc_id
    with _rpc_id_lock:
        _rpc_id += 1
        return _rpc_id


def _rpc_request(method: str, params: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id":      _next_id(),
        "method":  method,
        "params":  params,
    }


# ---------------------------------------------------------------------------
# Persistent MCP server handle
# ---------------------------------------------------------------------------

class _MCPServer:
    """
    Manages a single long-lived MCP server subprocess.

    The server is started once, initialized via JSON-RPC, and then kept alive
    for the lifetime of the Python process.  A background reader thread pushes
    incoming lines onto a queue; call() pulls the response matching its request id.
    """

    def __init__(self, server_key: str, cmd: list[str], env: dict) -> None:
        self.key = server_key
        self._lock = threading.Lock()   # one in-flight RPC at a time
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._pending: dict[int, queue.Queue[dict]] = {}
        self._pending_lock = threading.Lock()

        log.info("Starting MCP server '%s': %s", server_key, " ".join(cmd))
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
        assert self._proc.stdin is not None and self._proc.stdout is not None
        self._stdin  = self._proc.stdin
        self._stdout = self._proc.stdout

        # Background thread — reads stdout and dispatches to waiting callers
        self._reader_thread = threading.Thread(
            target=self._reader, daemon=True, name=f"mcp-reader-{server_key}"
        )
        self._reader_thread.start()

        # Also drain stderr to avoid blocking the subprocess
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, daemon=True, name=f"mcp-stderr-{server_key}"
        )
        self._stderr_thread.start()

        self._initialize()

    # ------------------------------------------------------------------
    # Background threads
    # ------------------------------------------------------------------

    def _reader(self) -> None:
        try:
            while True:
                line = self._stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    log.debug("[%s] non-JSON stdout: %s", self.key, line[:200])
                    continue
                msg_id = msg.get("id")
                if msg_id is not None:
                    with self._pending_lock:
                        q = self._pending.get(msg_id)
                    if q is not None:
                        q.put(msg)
                    else:
                        log.debug("[%s] unsolicited response id=%s", self.key, msg_id)
        except Exception as exc:
            log.error("[%s] reader thread died: %s", self.key, exc)
        finally:
            # Unblock any waiting callers
            with self._pending_lock:
                for q in self._pending.values():
                    q.put({"error": {"message": f"MCP server {self.key} process ended"}})

    def _drain_stderr(self) -> None:
        if self._proc.stderr is None:
            return
        try:
            for line in self._proc.stderr:
                log.debug("[%s] stderr: %s", self.key, line.rstrip())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # RPC
    # ------------------------------------------------------------------

    def _send(self, msg: dict) -> None:
        self._stdin.write(json.dumps(msg) + "\n")
        self._stdin.flush()

    def _rpc(self, method: str, params: dict, timeout: float = 90.0) -> dict:
        req = _rpc_request(method, params)
        req_id = req["id"]
        resp_q: queue.Queue[dict] = queue.Queue()
        with self._pending_lock:
            self._pending[req_id] = resp_q
        try:
            self._send(req)
            try:
                resp = resp_q.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError(
                    f"MCP server '{self.key}' timed out after {timeout}s "
                    f"on {method}"
                )
        finally:
            with self._pending_lock:
                self._pending.pop(req_id, None)

        if "error" in resp:
            raise RuntimeError(
                f"MCP server '{self.key}' returned error: {resp['error']}"
            )
        return resp.get("result", {})

    def _initialize(self) -> None:
        result = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "expense-agent", "version": "1.0"},
        }, timeout=120.0)
        log.debug("[%s] initialized: %s", self.key, result.get("serverInfo", {}))
        # Send the required initialized notification (no response expected)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def call(self, tool_name: str, arguments: dict, timeout: float = 90.0) -> Any:
        """Send tools/call and return the parsed result."""
        with self._lock:
            result = self._rpc("tools/call", {
                "name":      tool_name,
                "arguments": arguments,
            }, timeout=timeout)

        # MCP spec: result is in result["content"][0]["text"]
        content = result.get("content", [])
        if content and content[0].get("type") == "text":
            raw = content[0]["text"]
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"text": raw}
        return result

    def shutdown(self) -> None:
        try:
            self._stdin.close()
        except Exception:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()


# ---------------------------------------------------------------------------
# Server registry — one instance per server_key, created on first use
# ---------------------------------------------------------------------------

_servers: dict[str, _MCPServer] = {}
_servers_lock = threading.Lock()


def _build_env(server_key: str) -> dict:
    env = {**os.environ}
    if server_key == "cloudant":
        env.setdefault("COUCHDB_URL",      os.environ.get("CLOUDANT_URL", ""))
        env.setdefault("COUCHDB_USERNAME", "apikey")
        env.setdefault("COUCHDB_PASSWORD", os.environ.get("CLOUDANT_APIKEY", ""))
    if server_key == "s3":
        env.setdefault("AWS_ACCESS_KEY_ID",     os.environ.get("COS_HMAC_ACCESS_KEY", ""))
        env.setdefault("AWS_SECRET_ACCESS_KEY", os.environ.get("COS_HMAC_SECRET_KEY", ""))
        env.setdefault("AWS_REGION",            "us-south")
        env.setdefault("AWS_ENDPOINT_URL",      os.environ.get("COS_ENDPOINT", ""))
    return env


def _get_server(server_key: str) -> _MCPServer:
    with _servers_lock:
        if server_key not in _servers:
            npx = _resolve_exe("npx")
            cmds = {
                "gmail":    [npx, "-y", "@gongrzhe/server-gmail-autoauth-mcp"],
                "cloudant": [npx, "-y", "couchdb-mcp"],
                "s3":       [npx, "-y", "aws-s3-mcp"],
            }
            _servers[server_key] = _MCPServer(
                server_key,
                cmds[server_key],
                _build_env(server_key),
            )
        return _servers[server_key]


@atexit.register
def _shutdown_all() -> None:
    for srv in list(_servers.values()):
        try:
            srv.shutdown()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------

_MOCK_RESPONSES: dict[str, Any] = {
    "search_emails":       {"messages": []},
    "read_email":          {
        "id": "mock_msg_001",
        "threadId": "thread_001",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Expense - July"},
                {"name": "From",    "value": "test@example.com"},
            ],
            "parts": [],
        },
    },
    "download_attachment":  {},
    "modify_email":         {"id": "mock_msg_001", "labelIds": ["Processed"]},
    "send_email":           {"id": "mock_sent_001"},
    "get_or_create_label":  {"id": "Label_mock", "name": "Processed"},
    "create_document":      {"text": "Document created successfully"},
    "update_document":      {"text": "Document updated successfully"},
    "get_document":         {"_id": "mock_doc", "_rev": "1-abc"},
    "mango_query":          {"docs": []},
}


def _call_mock(tool_name: str, arguments: dict) -> Any:
    log.info("[MOCK] call_tool('%s', %s)", tool_name, arguments)
    if tool_name in _MOCK_RESPONSES:
        return _MOCK_RESPONSES[tool_name]
    log.warning("[MOCK] No canned response for '%s' — returning {}", tool_name)
    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def call_tool(tool: str, **kwargs) -> Any:
    """
    Call an MCP tool by name. Routes to the correct MCP server automatically.
    The server process is started once and reused across calls.

    Args:
        tool:     Tool name, e.g. "search_emails", "cloudant_upsert"
        **kwargs: Tool arguments passed directly to the MCP server.

    Returns:
        Parsed JSON response from the MCP server.

    Raises:
        ValueError:   if tool name doesn't match any registered server.
        RuntimeError: if the MCP server returns an error or times out.
    """
    mode = os.environ.get("MCP_MODE", "real").lower()
    if mode == "mock":
        return _call_mock(tool, kwargs)

    # Route to server
    server_key: str | None = None
    if tool in _GMAIL_TOOLS:
        server_key = "gmail"
    elif tool in _CLOUDANT_TOOLS:
        server_key = "cloudant"
    else:
        for prefix, key in _TOOL_SERVER_MAP.items():
            if tool.startswith(prefix):
                server_key = key
                break

    if server_key is None:
        raise ValueError(
            f"No MCP server registered for tool '{tool}'. "
            f"Known Gmail tools: {_GMAIL_TOOLS}, "
            f"known Cloudant tools: {_CLOUDANT_TOOLS}, "
            f"known prefixes: {list(_TOOL_SERVER_MAP.keys())}"
        )

    # download_attachment does two Gmail API round-trips — give it more time
    timeout = 120.0 if tool == "download_attachment" else 90.0
    return _get_server(server_key).call(tool, kwargs, timeout=timeout)
