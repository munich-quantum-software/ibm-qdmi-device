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

"""Resolve installed native artifacts without loading the device."""

from __future__ import annotations

import sys
from importlib.metadata import distribution
from pathlib import Path

IBM_QDMI_DEVICE_ID = "ibm.default"
IBM_QDMI_PREFIX = "IBM"
_DATA = Path(str(distribution("ibm-qdmi").locate_file("ibm/qdmi/data"))).resolve()
IBM_QDMI_INCLUDE_DIR = _DATA / "include"
IBM_QDMI_CMAKE_DIR = _DATA / "share" / "cmake"
_LIBRARY_DIR = _DATA / ("bin" if sys.platform == "win32" else "lib")
if sys.platform == "win32":
    _LIBRARY_NAMES = ("ibm-qdmi-device.dll", "libibm-qdmi-device.dll")
else:
    _LIBRARY_NAMES = ("libibm-qdmi-device." + ("dylib" if sys.platform == "darwin" else "so"),)
IBM_QDMI_LIBRARY_PATH = next(
    (_LIBRARY_DIR / name for name in _LIBRARY_NAMES if (_LIBRARY_DIR / name).is_file()),
    _LIBRARY_DIR / _LIBRARY_NAMES[0],
)
IBM_QDMI_CATALOG_PATH = _LIBRARY_DIR / "ibm-qdmi-device.qdmi.json"
