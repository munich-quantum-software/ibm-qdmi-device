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

"""Shared offline framework fixtures."""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

import pytest
from qiskit_service import RuntimeProxy, remote_runtime

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def runtime() -> Iterator[RuntimeProxy]:
    """Attach the synthetic runtime and release any Python job cycles.

    Yields:
        The loopback service and its recorded submissions.
    """
    with remote_runtime() as proxy:
        yield proxy
        gc.collect()
