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

"""Test-only bindings and lifetime management for the installed C ABI."""

from __future__ import annotations

import ctypes
import sys
from contextlib import contextmanager
from importlib import resources
from typing import TYPE_CHECKING

from ibm import qdmi

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


class MetadataError(Exception):
    """A fixed diagnostic category, optionally followed by a QDMI status."""


def check(status: int, category: str) -> None:
    """Reject a failed C call without including input or response values.

    Raises:
        MetadataError: The native call returned an error.
    """
    if status != 0:
        msg = f"{category}: QDMI status {status}"
        raise MetadataError(msg)


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
    def session(self, parameters: Mapping[int, str]) -> Iterator[ctypes.c_void_p]:
        """Allocate and configure a session; always free it afterward.

        Yields:
            An uninitialized native session handle.
        """
        handle = ctypes.c_void_p()
        check(self.alloc(ctypes.byref(handle)), "session allocation")
        try:
            for parameter, text in parameters.items():
                encoded = text.encode()
                check(self.set(handle, parameter, len(encoded) + 1, encoded), "session configuration")
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


@contextmanager
def load_native() -> Iterator[Native]:
    """Own the installed library lifecycle.

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
        check(api.initialize(), "device initialization")
        try:
            yield api
        finally:
            check(api.finalize(), "device finalization")
