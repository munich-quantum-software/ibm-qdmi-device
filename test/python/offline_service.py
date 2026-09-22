# Copyright (c) 2026 Munich Quantum Software Company GmbH
# All rights reserved.
#
# Licensed under the Apache License v2.0 with LLVM Exceptions (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://llvm.org/LICENSE.txt
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
#
# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception

"""Synthetic IBM service fixtures for offline tests only."""

from __future__ import annotations

import json
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from threading import Thread
from typing import TYPE_CHECKING, Any

import pytest
from native_support import Native, load_native

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::"


class LoopbackHTTPServer(ThreadingHTTPServer):
    """Serve loopback requests without resolving the server's hostname."""

    daemon_threads = False

    def server_bind(self) -> None:
        """Bind the socket and use the known local server name."""
        TCPServer.server_bind(self)
        self.server_name = "localhost"
        self.server_port = self.server_address[1]


@dataclass
class Service:
    """Mutable synthetic responses and recorded HTTP requests."""

    data: dict[str, Any] = field(
        default_factory=lambda: json.loads(
            (Path(__file__).parents[1] / "fixtures" / "backend.json").read_text(encoding="utf-8")
        )
    )
    errors: dict[str, int] = field(default_factory=dict)
    requests: list[tuple[str, dict[str, str], bytes]] = field(default_factory=list)
    url: str = ""
    respond: Callable[[str, bytes], tuple[int, Any]] | None = None

    @property
    def parameters(self) -> dict[int, str]:
        """Synthetic session parameters targeting only this server."""
        return {
            0: self.url,
            1: "synthetic-key",
            3: self.url + "/auth",
            999999995: "ibm_test",
            999999996: CRN,
        }


@contextmanager
def serve() -> Iterator[Service]:
    """Serve IBM-shaped responses without external network access.

    Yields:
        Mutable loopback service responses and request history.
    """
    state = Service()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # ruff: ignore[builtin-argument-shadowing]
            """Suppress request logging, including authentication data."""

        def respond(self, body: bytes) -> None:
            """Record the request and return the selected fixture response."""
            state.requests.append((self.path, dict(self.headers), body))
            key = self.path.rsplit("/", 1)[-1]
            status = state.errors.get(key, 200 if key in state.data else 404)
            data = state.data.get(key, {})
            if state.respond is not None and "/jobs" in self.path:
                status, data = state.respond(self.path, body)
            self.send_response(status)
            if status == 302:
                self.send_header("Location", state.url + "/redirect-target")
            # Timeout tests close the client before the delayed reply.
            with suppress(ConnectionError):
                self.end_headers()
                self.wfile.write(data.encode() if isinstance(data, str) else json.dumps(data).encode())

        def do_GET(self) -> None:
            """Handle a backend query."""
            self.respond(b"")

        def do_POST(self) -> None:
            """Handle the IAM form exchange."""
            self.respond(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

    with LoopbackHTTPServer(("127.0.0.1", 0), Handler) as server:
        state.url = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield state
        finally:
            server.shutdown()
            thread.join()


@pytest.fixture
def service() -> Iterator[Service]:
    """Own a loopback HTTP service for a native ctypes test.

    Yields:
        Mutable synthetic service state.
    """
    with serve() as state:
        yield state


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> Iterator[Native]:
    """Own the installed library lifecycle for an offline test.

    Yields:
        The initialized native interface.
    """
    for name in ("IBM_QUANTUM_API_KEY", "IBM_QUANTUM_INSTANCE_CRN", "IBM_QUANTUM_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    with load_native() as api:
        yield api
