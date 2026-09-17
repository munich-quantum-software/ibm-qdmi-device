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

"""Package metadata and native artifacts for the IBM QDMI Device."""

from __future__ import annotations

from ._paths import (
    IBM_QDMI_CATALOG_PATH,
    IBM_QDMI_CMAKE_DIR,
    IBM_QDMI_DEVICE_ID,
    IBM_QDMI_INCLUDE_DIR,
    IBM_QDMI_LIBRARY_PATH,
    IBM_QDMI_PREFIX,
)
from ._version import version as __version__

__all__ = [
    "IBM_QDMI_CATALOG_PATH",
    "IBM_QDMI_CMAKE_DIR",
    "IBM_QDMI_DEVICE_ID",
    "IBM_QDMI_INCLUDE_DIR",
    "IBM_QDMI_LIBRARY_PATH",
    "IBM_QDMI_PREFIX",
    "__version__",
]


def __dir__() -> list[str]:
    return __all__
