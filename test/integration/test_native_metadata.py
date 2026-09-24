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

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from urllib.parse import parse_qs

import metadata_checks
import pytest
from metadata_checks import validate_backend
from native_support import MetadataError, Native
from offline_service import CRN, Service

if TYPE_CHECKING:
    import ctypes
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
