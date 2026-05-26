"""Thin async wrapper over V8 Inspector Protocol via websockets.

V8 Inspector is the JSON-RPC protocol Chrome DevTools uses. Each
request carries an integer `id`; responses match by id. Some
messages are events (no `id`, but a `method` field) — the session
demuxes both streams and surfaces `Debugger.paused` events through
the `paused_events()` async generator.

The wire format is documented at
  https://chromedevtools.github.io/devtools-protocol/

We use only the surface we need: Debugger.{enable,paused,stepInto,
resume}, Runtime.{enable,runIfWaitingForDebugger,getProperties,
callFunctionOn,executionContextDestroyed}. Each method is one async
function on the session.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, Optional

import websockets


class InspectorError(RuntimeError):
    """Surface for inspector-side errors (malformed responses, RPC error
    codes, connection drops). Caller catches once at the orchestration
    layer to convert to an error-trace."""


class InspectorSession:
    """Active Inspector connection. One per `node --inspect-brk` instance.

    Usage:
        async with await InspectorSession.connect(ws_url) as session:
            await session.enable_domains()
            await session.run_if_waiting_for_debugger()
            async for paused in session.paused_events():
                ...
                await session.step_into()
    """

    def __init__(self, ws: "websockets.WebSocketClientProtocol") -> None:
        self._ws = ws
        self._next_id = 0
        self._pending: Dict[int, "asyncio.Future[dict]"] = {}
        self._events: "asyncio.Queue[dict]" = asyncio.Queue()
        self._closed = False
        self._reader_task: Optional[asyncio.Task] = None
        # V8 reports the script URL once via Debugger.scriptParsed —
        # not on every callFrame. We collect the map here so callers
        # can resolve callFrame.location.scriptId → url.
        self.script_urls: Dict[str, str] = {}

    @classmethod
    async def connect(cls, ws_url: str) -> "InspectorSession":
        ws = await websockets.connect(ws_url, max_size=10 * 1024 * 1024)
        session = cls(ws)
        session._reader_task = asyncio.create_task(session._reader_loop())
        return session

    async def __aenter__(self) -> "InspectorSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            await self._ws.close()
        except Exception:
            pass

    # ────────────────────────────────────────────────────────────────
    # Reader pump — demultiplexes responses from event notifications.
    # ────────────────────────────────────────────────────────────────

    async def _reader_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if "id" in msg:
                    fut = self._pending.pop(msg["id"], None)
                    if fut and not fut.done():
                        fut.set_result(msg)
                elif "method" in msg:
                    # Intercept scriptParsed so we don't need a separate
                    # queue consumer — every paused event will benefit
                    # from the up-to-date script→url map.
                    if msg.get("method") == "Debugger.scriptParsed":
                        p = msg.get("params") or {}
                        sid = p.get("scriptId")
                        if sid:
                            self.script_urls[sid] = p.get("url") or ""
                    await self._events.put(msg)
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass
        finally:
            # Wake any pending awaiters with a synthetic error so the
            # outer loop can exit cleanly when Node terminates.
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(InspectorError("inspector connection closed"))
            self._pending.clear()
            # Signal end-of-events.
            await self._events.put({"method": "__closed__"})

    # ────────────────────────────────────────────────────────────────
    # RPC layer
    # ────────────────────────────────────────────────────────────────

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._next_id += 1
        req_id = self._next_id
        payload = {"id": req_id, "method": method, "params": params or {}}
        fut: "asyncio.Future[dict]" = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as e:
            self._pending.pop(req_id, None)
            raise InspectorError(f"send failed: {e}") from e
        resp = await fut
        if "error" in resp:
            raise InspectorError(f"{method}: {resp['error'].get('message', resp['error'])}")
        return resp.get("result", {})

    # ────────────────────────────────────────────────────────────────
    # Domain helpers — thin pass-throughs that name the intent.
    # ────────────────────────────────────────────────────────────────

    async def enable_domains(self) -> None:
        await self.send("Debugger.enable")
        await self.send("Runtime.enable")

    async def run_if_waiting_for_debugger(self) -> None:
        await self.send("Runtime.runIfWaitingForDebugger")

    async def step_into(self) -> None:
        await self.send("Debugger.stepInto")

    async def resume(self) -> None:
        await self.send("Debugger.resume")

    async def get_properties(
        self,
        object_id: str,
        own_properties: bool = True,
        accessor_properties_only: bool = False,
    ) -> list:
        result = await self.send(
            "Runtime.getProperties",
            {
                "objectId": object_id,
                "ownProperties": own_properties,
                "accessorPropertiesOnly": accessor_properties_only,
                "generatePreview": False,
            },
        )
        return result.get("result", []) or []

    async def call_function_on(
        self, object_id: str, function_declaration: str
    ) -> Dict[str, Any]:
        """Run `function_declaration` with `this` bound to `objectId`.

        Used to invoke `[...this.entries()]` on Maps / Sets so we get
        a RemoteObject for the entries array we can then walk.
        """
        result = await self.send(
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": function_declaration,
                "returnByValue": False,
                "silent": True,
            },
        )
        return result.get("result", {}) or {}

    # ────────────────────────────────────────────────────────────────
    # Event stream
    # ────────────────────────────────────────────────────────────────

    async def paused_events(self) -> AsyncIterator[Dict[str, Any]]:
        """Yield each `Debugger.paused` event until the connection closes
        or `Runtime.executionContextDestroyed` fires."""
        while True:
            event = await self._events.get()
            method = event.get("method")
            if method == "__closed__":
                return
            if method == "Runtime.executionContextDestroyed":
                return
            if method == "Debugger.paused":
                yield event.get("params", {})


# ────────────────────────────────────────────────────────────────────
# Node bootstrap — spawn a `--inspect-brk` Node subprocess and
# discover its websocket URL from stderr. Used by the orchestrator
# in __init__.py; lives here so test fixtures can monkeypatch it.
# ────────────────────────────────────────────────────────────────────

import re
import subprocess


WS_URL_PATTERN = re.compile(r"ws://[^\s]+")


async def spawn_node_inspector(
    script_path: str, *, timeout_s: float = 5.0
) -> tuple[subprocess.Popen, str]:
    """Start `node --inspect-brk=127.0.0.1:0 <script>` and return
    (process, ws_url). Reads stderr (where Node prints the listener URL)
    with a short polling timeout so a misbehaving Node doesn't hang us.

    Caller must remember to `proc.terminate()` / `proc.wait()` in a
    `finally` so the subprocess isn't orphaned.
    """
    # Detach Node's stdin from the parent's. When the tracer is invoked
    # from inside a sandbox subprocess whose own stdin is a pipe (e.g.
    # the backend's _run_sandbox feeds source via stdin), Node would
    # otherwise inherit that pipe and stall on startup waiting for the
    # confused-deputy stdin to drain.
    proc = subprocess.Popen(
        ["node", "--inspect-brk=127.0.0.1:0", script_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    buf = ""
    while loop.time() < deadline:
        if proc.stderr is None:
            break
        # Run readline in the executor so we don't block the loop.
        line = await loop.run_in_executor(None, proc.stderr.readline)
        if not line:
            await asyncio.sleep(0.05)
            continue
        buf += line
        m = WS_URL_PATTERN.search(buf)
        if m:
            return proc, m.group(0)
    # Cleanup before raising.
    try:
        proc.terminate()
    except Exception:
        pass
    raise InspectorError("timed out waiting for Node Inspector ws URL")
