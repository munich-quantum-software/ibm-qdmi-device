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

"""Exercise installed QDMI metadata against Simulated Quantum Resource."""

from __future__ import annotations

import ctypes
from functools import partial
from typing import TYPE_CHECKING

import pytest
from metadata_checks import check, number, read, text, validate_snapshot
from offline_service import CRN

if TYPE_CHECKING:
    from native_support import Native

pytestmark = [pytest.mark.integration, pytest.mark.simulator]


@pytest.fixture
def simulator_parameters(pytestconfig: pytest.Config) -> dict[int, str]:
    """Configure explicit simulator endpoints and synthetic IAM credentials.

    Returns:
        Native session parameters that never fall back to IBM Cloud.
    """
    url = pytestconfig.getoption("simulator_url")
    return {
        0: url,
        1: "synthetic-key",
        3: url + "/identity/token",
        999999995: "fake_lagos",
        999999996: CRN,
        999999997: "5000",
    }


def test_simulator_metadata(native: Native, simulator_parameters: dict[int, str]) -> None:
    """Real IAM and backend responses satisfy the QDMI snapshot contracts."""
    with native.session(simulator_parameters) as session:
        check(native.init(session), "simulator session initialization")
        validate_snapshot(native, session, "fake_lagos", 7)
        for site in native.handles(session, 5):
            raw = read(partial(native.site, session, site, 1), "simulator T1")
            assert raw is not None
            assert ctypes.c_uint64.from_buffer_copy(raw).value > 0
        signatures = {}
        for operation in native.handles(session, 6):
            query = partial(native.operation, session, operation, 0, None, 0, None)
            signatures[text(partial(query, 0), "operation name")] = query
        assert number(partial(signatures["rz"], 1), "rz arity") == 1
        assert number(partial(signatures["rz"], 2), "rz parameter count") == 1


def test_simulator_rejects_invalid_api_key(native: Native, simulator_parameters: dict[int, str]) -> None:
    """The simulator's IAM rejection maps to QDMI permission denied."""
    with native.session({**simulator_parameters, 1: "invalid-synthetic-key"}) as session:
        assert native.init(session) == -8
