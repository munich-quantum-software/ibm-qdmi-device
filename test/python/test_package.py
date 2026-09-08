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

"""Verify the installed package, including its native artifacts."""

from __future__ import annotations

import ctypes
import sys
from importlib import metadata, resources

from ibm import qdmi


def test_version() -> None:
    """The import and distribution expose the same version."""
    assert qdmi.__version__ == metadata.version("ibm-qdmi")


def test_installed_artifacts() -> None:
    """Wheels include typing information, headers, and CMake exports."""
    package = resources.files(qdmi)
    assert package.joinpath("py.typed").is_file()
    data = package.joinpath("data")
    for header in ("device.h", "constants.h", "types.h", "export.h"):
        assert data.joinpath("include", "ibm_qdmi", header).is_file()
    for name in ("config", "config-version", "targets"):
        assert data.joinpath("share", "cmake", "ibm-qdmi-device", f"ibm-qdmi-device-{name}.cmake").is_file()


def test_native_library_loads() -> None:
    """The packaged library can be loaded without a backend SDK."""
    data = resources.files(qdmi).joinpath("data")
    if sys.platform == "win32":
        libraries = [
            path
            for path in data.joinpath("bin").iterdir()
            if path.name in {"ibm-qdmi-device.dll", "libibm-qdmi-device.dll"}
        ]
        assert len(libraries) == 1
        library = libraries[0]
    elif sys.platform == "darwin":
        library = data.joinpath("lib", "libibm-qdmi-device.dylib")
    else:
        library = data.joinpath("lib", "libibm-qdmi-device.so")
    with resources.as_file(library) as path:
        ctypes.CDLL(str(path))
