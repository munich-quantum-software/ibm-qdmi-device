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

"""Shared metadata checks for synthetic and explicitly authorized live tests."""

from __future__ import annotations

import ctypes
import math
from functools import partial
from typing import TYPE_CHECKING

from native_support import MetadataError, check

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from native_support import Native

    Query = Callable[[int, object, object], int]

BACKENDS = {"ibm_berlin": 120, "ibm_aachen": 156}


def require(condition: object, category: str) -> None:
    """Reject inconsistent metadata without exposing its values.

    Raises:
        MetadataError: The metadata violates a query contract.
    """
    if not condition:
        raise MetadataError(category)


def read(query: Query, category: str, *, optional: bool = False) -> bytes | None:
    """Exercise both stages of a QDMI size query.

    Returns:
        The returned bytes, or None for an unsupported optional property.
    """
    size = ctypes.c_size_t()
    status = query(0, None, ctypes.byref(size))
    if optional and status == -9:
        return None
    check(status, category)
    require(size.value <= 16 * 1024 * 1024, "query size limit")
    buffer = ctypes.create_string_buffer(size.value)
    actual = ctypes.c_size_t()
    check(query(size.value, buffer, ctypes.byref(actual)), category)
    require(actual.value == size.value, "query size consistency")
    return buffer.raw


def number(query: Query, category: str, *, optional: bool = False) -> int | None:
    """Read a size_t property.

    Returns:
        The integer value, or None when optional metadata is unsupported.
    """
    raw = read(query, category, optional=optional)
    if raw is None:
        return None
    require(len(raw) == ctypes.sizeof(ctypes.c_size_t), category)
    return ctypes.c_size_t.from_buffer_copy(raw).value


def text(query: Query, category: str) -> str:
    """Read a nonempty, null-terminated metadata string.

    Returns:
        The decoded string, retained only in memory.

    Raises:
        MetadataError: The required string is unavailable.
    """
    raw = read(query, category)
    require(raw is not None and len(raw) > 1 and raw.endswith(b"\0"), category)
    if raw is None:
        raise MetadataError(category)
    require(b"\0" not in raw[:-1], category)
    return raw[:-1].decode("utf-8")


def handles(query: Query, category: str, *, optional: bool = False) -> list[int] | None:
    """Read an opaque handle array.

    Returns:
        Non-null handles, or None for an unsupported optional query.
    """
    raw = read(query, category, optional=optional)
    if raw is None:
        return None
    width = ctypes.sizeof(ctypes.c_void_p)
    require(len(raw) % width == 0, category)
    values = list((ctypes.c_void_p * (len(raw) // width)).from_buffer_copy(raw))
    require(all(value is not None for value in values), category)
    return values


def duration(query: Query) -> None:
    """Check an optional unsigned picosecond value."""
    raw = read(query, "duration", optional=True)
    if raw is not None:
        require(len(raw) == ctypes.sizeof(ctypes.c_uint64), "duration type")
        require(ctypes.c_uint64.from_buffer_copy(raw).value >= 0, "duration range")


def validate_backend(api: Native, backend: str, expected_qubits: int, parameters: Mapping[int, str]) -> None:
    """Validate one snapshot and current status, freeing the session on failure.

    Raises:
        MetadataError: Metadata violates a query contract.
    """
    with api.session(parameters) as session:
        check(api.init(session), "session initialization")
        device = partial(api.device, session)
        require(text(partial(device, 0), "backend name") == backend, "backend identity")
        require(number(partial(device, 4), "qubit count") == expected_qubits, "qubit count")
        require(text(partial(device, 3), "QDMI version") == "1.3.3", "QDMI version")
        require(text(partial(device, 12), "duration unit") == "ps", "duration unit")
        scale = read(partial(device, 13), "duration scale")
        if scale is None:
            msg = "duration scale"
            raise MetadataError(msg)
        require(len(scale) == ctypes.sizeof(ctypes.c_double), "duration scale type")
        require(math.isclose(ctypes.c_double.from_buffer_copy(scale).value, 1.0), "duration scale")
        sites = handles(partial(device, 5), "site handles")
        require(sites is not None and len(sites) == expected_qubits, "site count")
        if sites is None:
            msg = "site handles"
            raise MetadataError(msg)
        require(len(set(sites)) == len(sites), "site uniqueness")
        indices = []
        for site in sites:
            indices.append(number(partial(api.site, session, site, 0), "site index"))
            for property_id in (1, 2):
                duration(partial(api.site, session, site, property_id))
        require(set(indices) == set(range(expected_qubits)), "physical indices")
        coupling = handles(partial(device, 7), "coupling handles")
        require(coupling is not None and len(coupling) % 2 == 0, "coupling shape")
        require(coupling is not None and set(coupling) <= set(sites), "coupling ownership")
        operations = handles(partial(device, 6), "operation handles")
        if operations is None:
            msg = "operation handles"
            raise MetadataError(msg)
        require(bool(operations) and len(set(operations)) == len(operations), "operation uniqueness")
        names = set()
        for operation in operations:
            general = partial(api.operation, session, operation, 0, None, 0, None)
            name = text(partial(general, 0), "operation name")
            require(name not in names, "operation names")
            names.add(name)
            arity = number(partial(general, 1), "operation arity", optional=True)
            if arity is not None:
                require(0 < arity <= expected_qubits, "operation arity")
            number(partial(general, 2), "parameter count", optional=True)
            tuples = handles(partial(general, 9), "operation sites", optional=True)
            if tuples is None:
                continue
            require(arity is not None and arity > 0, "operation tuple arity")
            if arity is None or arity == 0:
                msg = "operation tuple arity"
                raise MetadataError(msg)
            require(len(tuples) % arity == 0 and set(tuples) <= set(sites), "operation site ownership")
            for offset in range(0, len(tuples), arity):
                selected = tuples[offset : offset + arity]
                require(len(set(selected)) == arity, "operation tuple uniqueness")
                pointers = (ctypes.c_void_p * arity)(*selected)
                query = partial(api.operation, session, operation, arity, pointers, 0, None)
                duration(partial(query, 3))
                raw = read(partial(query, 4), "fidelity", optional=True)
                if raw is not None:
                    require(len(raw) == ctypes.sizeof(ctypes.c_double), "fidelity type")
                    fidelity = ctypes.c_double.from_buffer_copy(raw).value
                    require(math.isfinite(fidelity) and 0 <= fidelity <= 1, "fidelity range")
        status = read(partial(device, 2), "device status", optional=True)
        if status is not None:
            require(len(status) == ctypes.sizeof(ctypes.c_int), "device status type")
            require(ctypes.c_int.from_buffer_copy(status).value in range(6), "device status")
        number(partial(device, 17), "queue length")
