"""Experimental ACP stdio transport for explicitly trusted local agents.

ACP is a protocol, not a sandbox. This adapter is deliberately not registered
in the default Factory registry until its permission and isolation model is verified.
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from sf_factory.runtime import RuntimeResult


@dataclass(frozen=True)
class AcpCommand:
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.argv or any(not arg for arg in self.argv):
            raise ValueError("ACP command must be a non-empty argv sequence")


class AcpRuntime:
    """Run one ACP session via newline-delimited JSON-RPC over stdio."""

    def __init__(self, command: AcpCommand, name: str = "acp") -> None:
        self.command = command
        self.name = name

    def execute(
        self, *, prompt: str, workspace: Path, timeout_seconds: int = 600
    ) -> RuntimeResult:
        if not prompt.strip() or timeout_seconds < 1:
            raise ValueError("prompt and positive timeout required")
        workspace = workspace.expanduser().resolve()
        if not workspace.is_dir():
            raise ValueError("workspace must be an existing directory")
        deadline = time.monotonic() + timeout_seconds
        try:
            process = subprocess.Popen(
                list(self.command.argv),
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError:
            return self._failed("Unable to start ACP agent")
        events: queue.Queue[str | None] = queue.Queue()
        stdout = process.stdout
        stdin = process.stdin
        if stdout is None or stdin is None:
            process.kill()
            return self._failed("ACP stdio pipes unavailable")

        def reader() -> None:
            try:
                for line in stdout:
                    events.put(line)
            finally:
                events.put(None)

        threading.Thread(target=reader, daemon=True).start()
        request_id = 0
        output: list[str] = []
        stage = "initialize"
        try:
            def call(method: str, params: dict) -> dict:
                nonlocal request_id
                request_id += 1
                current_id = request_id
                message = {
                    "jsonrpc": "2.0", "id": current_id,
                    "method": method, "params": params,
                }
                stdin.write(json.dumps(message) + "\n")
                stdin.flush()
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    try:
                        raw = events.get(timeout=remaining)
                    except queue.Empty:
                        raise TimeoutError from None
                    if raw is None:
                        raise RuntimeError("ACP agent exited unexpectedly")
                    response = json.loads(raw)
                    if not isinstance(response, dict):
                        raise RuntimeError("Malformed ACP message")
                    if "method" in response:
                        method_name = response["method"]
                        if method_name == "session/update":
                            update = response.get("params", {}).get("update", {})
                            if update.get("sessionUpdate") == "agent_message_chunk":
                                content = update.get("content", {})
                                if content.get("type") == "text":
                                    output.append(content.get("text", ""))
                        elif "id" in response:
                            # Never approve agent-initiated filesystem/tool requests.
                            denied = {
                                "jsonrpc": "2.0", "id": response["id"],
                                "error": {"code": -32601, "message": "Denied by Factory"},
                            }
                            stdin.write(json.dumps(denied) + "\n")
                            stdin.flush()
                        continue
                    if response.get("id") != current_id:
                        raise RuntimeError("Unexpected ACP response ID")
                    if "error" in response:
                        raise RuntimeError("ACP agent returned an error")
                    result = response.get("result")
                    if not isinstance(result, dict):
                        raise RuntimeError("Malformed ACP response")
                    return result

            call("initialize", {
                "protocolVersion": 1,
                "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
                "clientInfo": {"name": "generic-software-factory", "version": "0.1.0"},
            })
            stage = "session/new"
            session = call("session/new", {
                "cwd": str(workspace), "mcpServers": [],
            })
            session_id = session.get("sessionId")
            if not isinstance(session_id, str) or not session_id:
                raise RuntimeError("ACP session ID missing")
            stage = "session/prompt"
            response = call("session/prompt", {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": prompt}],
            })
            stop_reason = response.get("stopReason")
            if stop_reason != "end_turn":
                raise RuntimeError("ACP session did not complete normally")
            return RuntimeResult(
                runtime=self.name, status="succeeded", output="".join(output),
                exit_code=0, session_id=session_id,
            )
        except TimeoutError:
            return RuntimeResult(
                runtime=self.name, status="timed_out", output="",
                exit_code=None, error_kind="timeout", error_message="ACP timed out",
            )
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
            # Report only the failure category and stage; never expose agent data,
            # remote error messages, file paths, or authentication details.
            return self._failed(f"ACP {stage} failed ({type(exc).__name__})")
        finally:
            process.kill()
            try:
                process.communicate(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _failed(self, message: str) -> RuntimeResult:
        return RuntimeResult(
            runtime=self.name, status="failed", output="", exit_code=None,
            error_kind="runtime_error", error_message=message,
        )
