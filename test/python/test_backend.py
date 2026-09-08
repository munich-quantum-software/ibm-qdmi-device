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

"""Exercise the installed C ABI against a synthetic loopback IBM service."""

from __future__ import annotations

import ctypes
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

import pytest

from ibm import qdmi

if TYPE_CHECKING:
    from collections.abc import Iterator

CRN = "crn:v1:bluemix:public:quantum-computing:us-east:a:instance::"


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


@pytest.fixture
def service() -> Iterator[Service]:
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
            self.send_response(status)
            if status == 302:
                self.send_header("Location", state.url + "/redirect-target")
            self.end_headers()
            data = state.data.get(key, {})
            self.wfile.write(data.encode() if isinstance(data, str) else json.dumps(data).encode())

        def do_GET(self) -> None:
            """Handle a backend query."""
            self.respond(b"")

        def do_POST(self) -> None:
            """Handle the IAM form exchange."""
            self.respond(self.rfile.read(int(self.headers.get("Content-Length", "0"))))

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        state.url = f"http://127.0.0.1:{server.server_port}"
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield state
        finally:
            server.shutdown()
            thread.join()


class Native:
    """Typed argument layout for the implemented QDMI entry points."""

    def __init__(self, path: str) -> None:
        """Load a packaged library and describe its C ABI."""
        self.library = ctypes.CDLL(path)
        pointer = ctypes.c_void_p
        size = ctypes.c_size_t
        size_pointer = ctypes.POINTER(size)
        self.initialize = self.library.IBM_QDMI_device_initialize
        self.finalize = self.library.IBM_QDMI_device_finalize
        self.alloc = self.library.IBM_QDMI_device_session_alloc
        self.free = self.library.IBM_QDMI_device_session_free
        self.set = self.library.IBM_QDMI_device_session_set_parameter
        self.init = self.library.IBM_QDMI_device_session_init
        self.device = self.library.IBM_QDMI_device_session_query_device_property
        self.site = self.library.IBM_QDMI_device_session_query_site_property
        self.operation = self.library.IBM_QDMI_device_session_query_operation_property
        for function, arguments in (
            (self.initialize, []),
            (self.finalize, []),
            (self.alloc, [ctypes.POINTER(pointer)]),
            (self.free, [pointer]),
            (self.set, [pointer, ctypes.c_int, size, pointer]),
            (self.init, [pointer]),
            (self.device, [pointer, ctypes.c_int, size, pointer, size_pointer]),
            (self.site, [pointer, pointer, ctypes.c_int, size, pointer, size_pointer]),
            (
                self.operation,
                [
                    pointer,
                    pointer,
                    size,
                    ctypes.POINTER(pointer),
                    size,
                    ctypes.POINTER(ctypes.c_double),
                    ctypes.c_int,
                    size,
                    pointer,
                    size_pointer,
                ],
            ),
        ):
            function.argtypes = arguments
            function.restype = ctypes.c_int
        self.free.restype = None

    @contextmanager
    def session(self, service: Service) -> Iterator[ctypes.c_void_p]:
        """Allocate and configure a session; always free it afterward.

        Yields:
            An uninitialized native session handle.
        """
        handle = ctypes.c_void_p()
        assert self.alloc(ctypes.byref(handle)) == 0
        try:
            for parameter, text in (
                (0, service.url),
                (1, "synthetic-key"),
                (3, service.url + "/auth"),
                (999999995, "ibm_test"),
                (999999996, CRN),
            ):
                encoded = text.encode()
                assert self.set(handle, parameter, len(encoded) + 1, encoded) == 0
            yield handle
        finally:
            self.free(handle)

    def handles(self, handle: ctypes.c_void_p, property_id: int) -> list[int]:
        """Read a site, operation, or coupling handle array using size queries.

        Returns:
            Opaque handles owned by the session.
        """
        size = ctypes.c_size_t()
        assert self.device(handle, property_id, 0, None, ctypes.byref(size)) == 0
        values = (ctypes.c_void_p * (size.value // ctypes.sizeof(ctypes.c_void_p)))()
        assert self.device(handle, property_id, size.value, values, None) == 0
        return list(values)


@pytest.fixture
def native() -> Iterator[Native]:
    """Initialize the installed native library for each test.

    Yields:
        The initialized native interface.
    """
    data = resources.files(qdmi).joinpath("data")
    if sys.platform == "win32":
        library = next(
            path
            for path in data.joinpath("bin").iterdir()
            if path.name in {"ibm-qdmi-device.dll", "libibm-qdmi-device.dll"}
        )
    else:
        library = data.joinpath("lib", "libibm-qdmi-device." + ("dylib" if sys.platform == "darwin" else "so"))
    with resources.as_file(library) as path:
        api = Native(str(path))
        assert api.initialize() == 0
        yield api
        assert api.finalize() == 0


def test_query_contract(native: Native, service: Service) -> None:
    """Expose typed metadata and directed operation applicability through C."""
    with native.session(service) as session:
        assert native.device(session, 0, 0, None, None) == -10
        assert native.init(session) == 0
        assert native.init(session) == -10
        assert native.set(session, 1, 0, None) == -10
        required = ctypes.c_size_t()
        assert native.device(session, 0, 999, None, ctypes.byref(required)) == 0
        assert required.value == len("ibm_test") + 1
        name = ctypes.create_string_buffer(required.value)
        assert native.device(session, 0, required.value - 1, name, None) == -7
        assert name.value == b""
        assert native.device(session, 0, required.value, name, None) == 0
        assert name.value == b"ibm_test"
        assert native.device(session, 18, 0, None, None) == -7
        assert native.device(session, 15, 0, None, None) == -9  # No executable formats yet.
        assert native.device(session, 16, 0, None, None) == -9  # No child devices.
        sites = native.handles(session, 5)
        assert len(sites) == 2
        assert native.handles(session, 7) == sites  # Only the directed pair (0, 1).
        value = ctypes.c_uint64()
        assert native.site(session, sites[0], 1, ctypes.sizeof(value), ctypes.byref(value), None) == 0
        assert value.value == 100500000
        assert native.site(session, sites[1], 1, 0, None, None) == -9
        operations = native.handles(session, 6)
        selected = (ctypes.c_void_p * 2)(*sites)
        assert (
            native.operation(
                session, operations[2], 2, selected, 0, None, 3, ctypes.sizeof(value), ctypes.byref(value), None
            )
            == 0
        )
        assert value.value == 35556
        reverse = (ctypes.c_void_p * 2)(*reversed(sites))
        assert native.operation(session, operations[2], 2, reverse, 0, None, 3, 0, None, None) == -9
        assert native.operation(session, operations[2], 0, None, 0, None, 3, 0, None, None) == -9
        status = ctypes.c_int()
        assert native.device(session, 2, ctypes.sizeof(status), ctypes.byref(status), None) == 0
        assert status.value == 2
        service.data["status"] = {"state": False, "length_queue": 0}
        assert native.device(session, 2, ctypes.sizeof(status), ctypes.byref(status), None) == 0
        assert status.value == 0
    assert all("/jobs" not in path for path, _, _ in service.requests)
    path, headers, body = service.requests[0]
    assert path == "/auth"
    assert "Authorization" not in headers
    assert parse_qs(body.decode())["apikey"] == ["synthetic-key"]
    for _, headers, body in service.requests[1:]:
        assert headers["Authorization"] == "Bearer synthetic-bearer"
        assert headers["Service-CRN"] == CRN
        assert headers["IBM-API-Version"] == "2026-04-15"
        assert body == b""


def test_session_isolation_and_snapshot(native: Native, service: Service) -> None:
    """Sessions reject foreign handles and retain their initialization snapshot."""
    with native.session(service) as first, native.session(service) as second:
        assert native.init(first) == 0
        assert native.init(second) == 0
        sites = native.handles(first, 5)
        operations = native.handles(first, 6)
        assert native.site(second, sites[0], 0, 0, None, None) == -7
        assert native.operation(second, operations[0], 0, None, 0, None, 0, 0, None, None) == -7
        service.data["properties"] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: native.site(first, sites[0], 1, 0, None, None), range(12)))
        assert results == [0] * 12
        assert sum(path == "/auth" for path, _, _ in service.requests) == 2
        with native.session(service) as third:
            assert native.init(third) == 0
            assert native.site(third, native.handles(third, 5)[0], 1, 0, None, None) == -9
    assert native.init(first) == -7
    native.free(first)


@pytest.mark.parametrize(
    ("endpoint", "status", "expected"),
    [
        ("auth", 400, -8),
        ("auth", 403, -8),
        ("configuration", 401, -8),
        ("configuration", 403, -8),
        ("configuration", 404, -5),
        ("configuration", 429, -1),
        ("configuration", 500, -1),
        ("configuration", 302, -1),
    ],
)
def test_http_failure_and_recovery(native: Native, service: Service, endpoint: str, status: int, expected: int) -> None:
    """Failed initialization stays configurable and never follows redirects."""
    service.errors[endpoint] = status
    with native.session(service) as session:
        assert native.init(session) == expected
        assert native.set(session, 1, 0, None) == 0
        assert all(path != "/redirect-target" for path, _, _ in service.requests)
        service.errors.clear()
        assert native.init(session) == 0


@pytest.mark.parametrize("body", ["not json", {"backend_name": "ibm_test"}])
def test_malformed_metadata(native: Native, service: Service, body: object) -> None:
    """Parsing failures become status codes, not escaping C++ exceptions."""
    service.data["configuration"] = body
    with native.session(service) as session:
        assert native.init(session) == -1


def test_missing_calibration(native: Native, service: Service) -> None:
    """Absent calibration does not make the backend inaccessible."""
    service.errors["properties"] = 404
    with native.session(service) as session:
        assert native.init(session) == 0
        assert native.site(session, native.handles(session, 5)[0], 1, 0, None, None) == -9


@pytest.mark.parametrize("kind", ["qubit", "gate"])
@pytest.mark.parametrize("flag", [0, False, 1, True])
def test_faulty_operation_sites(native: Native, service: Service, kind: str, *, flag: int | bool) -> None:
    """Faulty qubits and gate calibrations remove applicable operation tuples."""
    parameter = {"name": "operational", "value": flag, "unit": ""}
    if kind == "qubit":
        service.data["properties"]["qubits"][0].append(parameter)
    else:
        service.data["properties"]["gates"][0]["parameters"].append(parameter)
    with native.session(service) as session:
        assert native.init(session) == 0
        sites = native.handles(session, 5)
        assert len(sites) == 2
        operations = native.handles(session, 6)
        selected = (ctypes.c_void_p * 2)(*sites)
        status = 0 if flag else -9
        assert native.operation(session, operations[2], 0, None, 0, None, 9, 0, None, None) == status
        for property_id in (3, 4):
            assert native.operation(session, operations[2], 2, selected, 0, None, property_id, 0, None, None) == status
        supported = (ctypes.c_void_p * 2)()
        required = ctypes.c_size_t()
        assert (
            native.operation(
                session, operations[0], 0, None, 0, None, 9, ctypes.sizeof(supported), supported, ctypes.byref(required)
            )
            == 0
        )
        expected = sites[1:] if kind == "qubit" and not flag else sites
        assert list(supported)[: len(expected)] == expected
        assert required.value == len(expected) * ctypes.sizeof(ctypes.c_void_p)


def test_invalid_arguments(native: Native, service: Service) -> None:
    """Reject null handles and invalid string sizes without network access."""
    assert native.alloc(None) == -7
    assert native.init(None) == -7
    assert native.device(None, 0, 0, None, None) == -7
    with native.session(service) as session:
        assert native.set(session, 1, 0, b"x") == -7
        assert native.set(session, 1, 1, b"x") == -7
        assert native.set(session, 1, 4, b"a\0b\0") == -7
        assert native.set(session, 7, 0, None) == -7
        assert native.set(session, 2, 0, None) == -9
        assert native.set(session, 1, 1, b"\0") == 0
        assert native.init(session) == -8
    assert service.requests == []


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        {"access_token": "", "expires_in": 3600},
        {"access_token": "synthetic", "expires_in": -1},
        {"access_token": "synthetic", "expires_in": "3600"},
    ],
)
def test_malformed_auth(native: Native, service: Service, body: object) -> None:
    """Invalid IAM responses fail without sending backend requests."""
    service.data["auth"] = body
    with native.session(service) as session:
        assert native.init(session) == -1
    assert [path for path, _, _ in service.requests] == ["/auth"]
