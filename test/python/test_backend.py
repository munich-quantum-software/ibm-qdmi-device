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
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import metadata_checks
import pytest
from metadata_checks import validate_backend
from native_support import MetadataError, Native
from offline_service import CRN, Service

if TYPE_CHECKING:
    from pathlib import Path

    from metadata_checks import Query


@pytest.mark.parametrize("optional", [True, False])
def test_live_checker_offline(native: Native, service: Service, *, optional: bool) -> None:
    """Validate real C queries with optional metadata present or unsupported."""
    if not optional:
        service.errors["properties"] = 404
        service.data["status"].pop("state")
        service.data["configuration"]["gates"] = []
    validate_backend(native, "ibm_test", 2, service.parameters)
    assert sum(path == "/auth" for path, _, _ in service.requests) == 1
    assert all(
        path.rsplit("/", 1)[-1] in {"auth", "configuration", "properties", "status"} for path, _, _ in service.requests
    )


@pytest.mark.parametrize(
    ("failure", "category"),
    [("count", "qubit count"), ("authentication", "session initialization: QDMI status -8")],
)
def test_live_checker_failure_cleanup(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, failure: str, category: str
) -> None:
    """Failures report fixed categories and free the allocated native session."""
    freed = []
    original = native.free

    def free(handle: ctypes.c_void_p) -> None:
        original(handle)
        freed.append(handle)

    monkeypatch.setattr(native, "free", free)
    if failure == "authentication":
        service.errors["auth"] = 403
    with pytest.raises(MetadataError, match=f"^{category}$"):
        validate_backend(native, "ibm_test", 3 if failure == "count" else 2, service.parameters)
    assert len(freed) == 1
    assert native.init(freed[0]) == -7


@pytest.mark.parametrize("category", ["coupling handles", "operation sites", "site handles"])
def test_live_checker_rejects_foreign_handles(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, category: str
) -> None:
    """Detect foreign coupling sites, incomplete operation tuples, and duplicate sites."""
    original = metadata_checks.handles

    def corrupt(query: Query, name: str, *, optional: bool = False) -> list[int] | None:
        values = original(query, name, optional=optional)
        if name == category and values:
            if name == "site handles":
                return [values[0]] * len(values)
            if name == "coupling handles":
                return [1, 1]
            return [*values, 1]
        return values

    monkeypatch.setattr(metadata_checks, "handles", corrupt)
    with pytest.raises(MetadataError):
        validate_backend(native, "ibm_test", 2, service.parameters)


def test_query_contract(native: Native, service: Service) -> None:
    """Expose typed metadata and directed operation applicability through C."""
    with native.session(service.parameters) as session:
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
        program_format = ctypes.c_int()
        assert native.device(session, 15, ctypes.sizeof(program_format), ctypes.byref(program_format), None) == 0
        assert program_format.value == 1  # OpenQASM 3.
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
    with native.session(service.parameters) as first, native.session(service.parameters) as second:
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
        with native.session(service.parameters) as third:
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
    with native.session(service.parameters) as session:
        assert native.init(session) == expected
        assert native.set(session, 1, 0, None) == 0
        assert all(path != "/redirect-target" for path, _, _ in service.requests)
        service.errors.clear()
        assert native.init(session) == 0


@pytest.mark.parametrize("body", ["not json", {"backend_name": "ibm_test"}])
def test_malformed_metadata(native: Native, service: Service, body: object) -> None:
    """Parsing failures become status codes, not escaping C++ exceptions."""
    service.data["configuration"] = body
    with native.session(service.parameters) as session:
        assert native.init(session) == -1


def test_missing_calibration(native: Native, service: Service) -> None:
    """Absent calibration does not make the backend inaccessible."""
    service.errors["properties"] = 404
    with native.session(service.parameters) as session:
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
    with native.session(service.parameters) as session:
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
    with native.session(service.parameters) as session:
        assert native.set(session, 1, 0, b"x") == -7
        assert native.set(session, 1, 1, b"x") == -7
        assert native.set(session, 1, 4, b"a\0b\0") == -7
        assert native.set(session, 7, 0, None) == -7
        assert native.set(session, 2, 0, None) == 0
        assert native.set(session, 1, 1, b"\0") == 0
        assert native.init(session) == -8
    assert service.requests == []


def test_native_environment_and_session_isolation(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resolve missing configuration at initialization and retain session values."""
    parameters = {key: value for key, value in service.parameters.items() if key in {0, 3}}
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "first-synthetic-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", CRN)
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_test")
    with native.session(parameters) as first, native.session(parameters) as second:
        for parameter in (1, 2, 999999995, 999999996, 999999997):
            assert native.set(first, parameter, 0, None) == 0
        assert service.requests == []
        assert native.init(first) == 0
        monkeypatch.setenv("IBM_QUANTUM_API_KEY", "second-synthetic-key")
        monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", CRN.replace(":instance::", ":second::"))
        assert native.init(second) == 0
        assert native.device(first, 2, 0, None, None) == 0
        assert service.requests[-1][1]["Service-CRN"] == CRN
        assert native.device(second, 2, 0, None, None) == 0
        assert service.requests[-1][1]["Service-CRN"] == CRN.replace(":instance::", ":second::")
    keys = [parse_qs(body.decode())["apikey"] for path, _, body in service.requests if path == "/auth"]
    assert keys == [["first-synthetic-key"], ["second-synthetic-key"]]


@pytest.mark.parametrize(("parameter", "expected"), [(1, -8), (999999995, -7), (999999996, -7)])
def test_explicit_values_override_environment(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, parameter: int, expected: int
) -> None:
    """Explicit values win, including empty values that remain invalid."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "environment-key")
    monkeypatch.setenv("IBM_QUANTUM_INSTANCE_CRN", CRN)
    monkeypatch.setenv("IBM_QUANTUM_BACKEND", "ibm_test")
    with native.session({**service.parameters, parameter: ""}) as session:
        assert native.init(session) == expected
        assert service.requests == []
        encoded = service.parameters[parameter].encode()
        assert native.set(session, parameter, len(encoded) + 1, encoded) == 0
        assert native.init(session) == 0
    assert parse_qs(service.requests[0][2].decode())["apikey"] == ["synthetic-key"]


def test_failed_initialization_resolves_environment_again(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed attempt does not freeze the resolved environment defaults."""
    parameters = {key: value for key, value in service.parameters.items() if key != 1}
    with native.session(parameters) as session:
        assert native.init(session) == -8
        assert service.requests == []
        monkeypatch.setenv("IBM_QUANTUM_API_KEY", "synthetic-recovered-key")
        assert native.init(session) == 0
    assert parse_qs(service.requests[0][2].decode())["apikey"] == ["synthetic-recovered-key"]


@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_auth_file_precedes_environment(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ending: bytes
) -> None:
    """Read an explicit UTF-8 key file without trimming the key itself."""
    path = tmp_path / "synthetic-schlüssel.txt"
    key = "synthetic-ä-key"
    path.write_bytes(key.encode() + ending)
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "environment-key")
    parameters = {parameter: value for parameter, value in service.parameters.items() if parameter != 1}
    with native.session({**parameters, 2: str(path)}) as session:
        assert native.init(session) == 0
    assert parse_qs(service.requests[0][2].decode())["apikey"] == [key]


def test_explicit_token_precedes_auth_file(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit token prevents all file access, even for an invalid path."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "environment-key")
    with native.session({**service.parameters, 2: str(tmp_path / "absent")}) as session:
        assert native.init(session) == 0
    assert parse_qs(service.requests[0][2].decode())["apikey"] == ["synthetic-key"]


def test_auth_file_is_a_session_snapshot(native: Native, service: Service, tmp_path: Path) -> None:
    """IAM refresh retains the initialized key when the selected file changes."""
    path = tmp_path / "synthetic-key.txt"
    path.write_text("original-key", encoding="utf-8")
    parameters = {parameter: value for parameter, value in service.parameters.items() if parameter != 1}
    with native.session({**parameters, 2: str(path)}) as session:
        assert native.init(session) == 0
        path.write_text("replacement-key", encoding="utf-8")
        service.errors["status"] = 401
        assert native.device(session, 2, 0, None, None) == -8
    keys = [parse_qs(body.decode())["apikey"] for endpoint, _, body in service.requests if endpoint == "/auth"]
    assert keys == [["original-key"], ["original-key"]]


@pytest.mark.parametrize("content", [b"", b"\n", b"key\n\n", b"key\r", b"ke\ny", b"ke\ry", b"ke\0y", b"key\xff"])
def test_invalid_auth_file_and_recovery(
    native: Native, service: Service, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, content: bytes
) -> None:
    """Malformed key files fail before IAM and remain configurable."""
    path = tmp_path / "synthetic-key.txt"
    path.write_bytes(content)
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "environment-key")
    parameters = {parameter: value for parameter, value in service.parameters.items() if parameter != 1}
    with native.session({**parameters, 2: str(path)}) as session:
        assert native.init(session) == -7
        assert service.requests == []
        path.write_text("recovered-key", encoding="utf-8")
        assert native.init(session) == 0
    assert parse_qs(service.requests[0][2].decode())["apikey"] == ["recovered-key"]


@pytest.mark.parametrize(("path_value", "expected"), [("", -7), ("absent", -8)])
def test_unreadable_auth_file_does_not_fall_back(
    native: Native,
    service: Service,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    path_value: str,
    expected: int,
) -> None:
    """A selected key file never silently falls back to environment credentials."""
    monkeypatch.setenv("IBM_QUANTUM_API_KEY", "environment-key")
    parameters = {parameter: value for parameter, value in service.parameters.items() if parameter != 1}
    with native.session({**parameters, 2: str(tmp_path / path_value) if path_value else ""}) as session:
        assert native.init(session) == expected
    assert service.requests == []


@pytest.mark.parametrize("timeout", [b"", b"0", b"-1", b"+1", b" 1", b"1ms", b"2147483648"])
def test_request_timeout_parameter(native: Native, service: Service, timeout: bytes) -> None:
    """Reject invalid timeouts without changing a previously valid setting."""
    with native.session({**service.parameters, 999999997: "2147483647"}) as session:
        assert native.set(session, 999999997, len(timeout) + 1, timeout + b"\0") == -7
        assert native.set(session, 999999997, 0, None) == 0
        assert native.init(session) == 0
        assert native.set(session, 999999997, 0, None) == -10


@pytest.mark.parametrize(("property_id", "value_type"), [(8, ctypes.c_size_t), (9, ctypes.c_int)])
def test_explicit_negative_capabilities(
    native: Native, service: Service, property_id: int, value_type: type[ctypes.c_size_t | ctypes.c_int]
) -> None:
    """Report no client calibration or pulse support with correct C value types."""
    with native.session(service.parameters) as session:
        assert native.device(session, property_id, 0, None, None) == -10
        assert native.init(session) == 0
        requests = len(service.requests)
        required = ctypes.c_size_t()
        assert native.device(session, property_id, 0, None, ctypes.byref(required)) == 0
        assert required.value == ctypes.sizeof(value_type)
        result = value_type(123)
        assert native.device(session, property_id, required.value - 1, ctypes.byref(result), None) == -7
        assert result.value == 123
        assert native.device(session, property_id, required.value, ctypes.byref(result), None) == 0
        assert result.value == 0
        assert len(service.requests) == requests


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
    with native.session(service.parameters) as session:
        assert native.init(session) == -1
    assert [path for path, _, _ in service.requests] == ["/auth"]
